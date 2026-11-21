"""
Connexion de Claude à l'appli (OAuth 2.1), pour le serveur MCP.

Le parcours, vu de la personne :
  1. dans Claude, elle ajoute le connecteur https://<domaine>/mcp ;
  2. Claude ouvre la page « Autoriser » de l'appli (connexion avec son compte
     habituel si besoin) ;
  3. elle clique sur « Autoriser » : Claude reçoit un jeton et agit ensuite
     avec ce compte (ex. « coché par Parent 1 »).

Côté technique, Claude suit la spécification d'autorisation MCP :
  - il lit /.well-known/oauth-protected-resource puis
    /.well-known/oauth-authorization-server ;
  - il s'enregistre tout seul (/oauth/enregistrer/, « Dynamic Client
    Registration ») ;
  - il obtient un code (/oauth/autoriser/, avec PKCE S256) puis des jetons
    (/oauth/jeton/), qu'il renouvelle avant expiration.

Seules les empreintes SHA-256 des codes et jetons sont enregistrées.
"""
import base64
import datetime
import hashlib
import json
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import ClientOAuth, CodeOAuth, JetonOAuth

PORTEE = "menus"
DUREE_CODE = datetime.timedelta(minutes=10)
DUREE_ACCES = datetime.timedelta(hours=1)
# Renouvelé à chaque utilisation : Claude ne redemande la connexion qu'après
# 90 jours sans aucune utilisation.
DUREE_RAFRAICHISSEMENT = datetime.timedelta(days=90)

# Adresses de retour acceptées : celle des applis Claude (web, ordinateur,
# téléphone) et, pour Claude Code, une adresse locale de l'ordinateur.
HOTES_CLAUDE = {"claude.ai", "claude.com"}
CHEMIN_RETOUR_CLAUDE = "/api/mcp/auth_callback"
HOTES_LOCAUX = {"localhost", "127.0.0.1"}


# --------------------------------------------------------------------------- outils

def empreinte(valeur):
    return hashlib.sha256(valeur.encode()).hexdigest()


def url_base(request):
    """https://<domaine> tel que Claude le voit. En production, toujours en
    HTTPS : Claude n'accepte pas autre chose, et le proxy du NAS fait le HTTPS."""
    schema = "https" if (request.is_secure() or not settings.DEBUG) else request.scheme
    return f"{schema}://{request.get_host()}"


def url_mcp(request):
    return url_base(request) + "/mcp"


def _redirection_autorisee(uri):
    try:
        p = urlsplit(uri)
    except ValueError:
        return False
    if p.fragment or not p.hostname:
        return False
    if p.scheme == "https" and p.hostname in HOTES_CLAUDE and p.path == CHEMIN_RETOUR_CLAUDE:
        return True
    return p.scheme == "http" and p.hostname in HOTES_LOCAUX


def _meme_redirection(demandee, enregistree):
    """Comparaison exacte, sauf pour les adresses locales (Claude Code) dont le
    port change à chaque session (RFC 8252, §7.3)."""
    if demandee == enregistree:
        return True
    try:
        a, b = urlsplit(demandee), urlsplit(enregistree)
    except ValueError:
        return False
    return (a.scheme == b.scheme == "http" and a.hostname in HOTES_LOCAUX and a.hostname == b.hostname
            and a.path == b.path and a.query == b.query)


def _avec_parametres(uri, **params):
    p = urlsplit(uri)
    requete = parse_qsl(p.query, keep_blank_values=True) + [(k, v) for k, v in params.items() if v is not None]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(requete), ""))


def _erreur(code, description, statut=400):
    r = JsonResponse({"error": code, "error_description": description}, status=statut)
    r["Cache-Control"] = "no-store"
    return r


def _pkce(verificateur):
    condense = hashlib.sha256(verificateur.encode("ascii")).digest()
    return base64.urlsafe_b64encode(condense).rstrip(b"=").decode("ascii")


# --------------------------------------------------------------------------- découverte

@require_GET
def metadonnees_ressource(request):
    """RFC 9728 : « pour utiliser /mcp, adressez-vous à ce serveur d'autorisation »."""
    base = url_base(request)
    return JsonResponse({
        "resource": base + "/mcp",
        "authorization_servers": [base],
        "scopes_supported": [PORTEE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Menus famille",
    })


@require_GET
def metadonnees_serveur(request):
    """RFC 8414 : adresses des étapes de connexion."""
    base = url_base(request)
    return JsonResponse({
        "issuer": base,
        "authorization_endpoint": base + "/oauth/autoriser/",
        "token_endpoint": base + "/oauth/jeton/",
        "registration_endpoint": base + "/oauth/enregistrer/",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [PORTEE],
    })


# --------------------------------------------------------------------------- enregistrement

@csrf_exempt
@require_POST
def enregistrer(request):
    """RFC 7591 : Claude s'enregistre tout seul à chaque nouvelle connexion."""
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _erreur("invalid_client_metadata", "Corps JSON illisible.")
    if not isinstance(data, dict):
        return _erreur("invalid_client_metadata", "Un objet JSON est attendu.")
    uris = data.get("redirect_uris")
    if not isinstance(uris, list) or not uris or not all(isinstance(u, str) and _redirection_autorisee(u) for u in uris):
        return _erreur("invalid_redirect_uri", "Seules les adresses de retour de Claude sont acceptées.")

    # Ménage : enregistrements de plus d'un jour qui n'ont mené à aucune connexion.
    ClientOAuth.objects.filter(cree_le__lt=timezone.now() - datetime.timedelta(days=1), jetons__isnull=True).delete()

    client = ClientOAuth.objects.create(
        client_id=secrets.token_urlsafe(24), nom=str(data.get("client_name") or "")[:200], redirect_uris=uris)
    return JsonResponse({
        "client_id": client.client_id,
        "client_id_issued_at": int(client.cree_le.timestamp()),
        "client_name": client.nom,
        "redirect_uris": client.redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, status=201)


# --------------------------------------------------------------------------- autorisation

@require_http_methods(["GET", "POST"])
def autoriser(request):
    """Page « Autoriser Claude ? » (GET), puis décision de la personne (POST)."""
    p = request.GET if request.method == "GET" else request.POST
    client = ClientOAuth.objects.filter(client_id=p.get("client_id", "")).first()
    redirect_uri = p.get("redirect_uri", "")
    if not client:
        return render(request, "menus/oauth_erreur.html", {
            "message": "Cette application n'est pas enregistrée. Retirez le connecteur dans Claude et ajoutez-le à nouveau."},
            status=400)
    if not redirect_uri or not any(_meme_redirection(redirect_uri, u) for u in client.redirect_uris):
        return render(request, "menus/oauth_erreur.html", {"message": "Adresse de retour non autorisée."}, status=400)

    # À partir d'ici, les erreurs sont renvoyées à Claude par l'adresse de retour.
    etat = p.get("state")
    if p.get("response_type") != "code":
        return HttpResponseRedirect(_avec_parametres(redirect_uri, error="unsupported_response_type", state=etat))
    challenge = p.get("code_challenge", "")
    if not 43 <= len(challenge) <= 128 or p.get("code_challenge_method") != "S256":
        return HttpResponseRedirect(_avec_parametres(
            redirect_uri, error="invalid_request", error_description="PKCE (S256) obligatoire.", state=etat))

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    if request.method == "POST":
        if p.get("decision") != "autoriser":
            return HttpResponseRedirect(_avec_parametres(redirect_uri, error="access_denied", state=etat))
        code = secrets.token_urlsafe(32)
        CodeOAuth.objects.filter(expire_le__lt=timezone.now()).delete()
        CodeOAuth.objects.create(
            code_hash=empreinte(code), client=client, utilisateur=request.user, redirect_uri=redirect_uri,
            code_challenge=challenge, scope=PORTEE, expire_le=timezone.now() + DUREE_CODE)
        return HttpResponseRedirect(_avec_parametres(redirect_uri, code=code, state=etat))

    hote = urlsplit(redirect_uri).hostname
    return render(request, "menus/oauth_autoriser.html", {
        "onglet": "", "client": client, "hote": hote, "local": hote in HOTES_LOCAUX,
        "champs": {k: p.get(k, "") for k in ("client_id", "redirect_uri", "response_type", "state",
                                              "code_challenge", "code_challenge_method", "scope", "resource")},
    })


# --------------------------------------------------------------------------- jetons

def _emettre(jeton, client, utilisateur):
    """Crée (ou renouvelle, en remplaçant les anciens) un couple de jetons."""
    acces, rafraichissement = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    maintenant = timezone.now()
    if jeton is None:
        jeton = JetonOAuth(client=client, utilisateur=utilisateur, scope=PORTEE)
    jeton.acces_hash = empreinte(acces)
    jeton.acces_expire_le = maintenant + DUREE_ACCES
    jeton.rafraichissement_hash = empreinte(rafraichissement)
    jeton.rafraichissement_expire_le = maintenant + DUREE_RAFRAICHISSEMENT
    jeton.save()
    r = JsonResponse({
        "access_token": acces, "token_type": "Bearer", "expires_in": int(DUREE_ACCES.total_seconds()),
        "refresh_token": rafraichissement, "scope": PORTEE,
    })
    r["Cache-Control"] = "no-store"
    r["Pragma"] = "no-cache"
    return r


@csrf_exempt
@require_POST
def jeton(request):
    """Échange d'un code (première connexion) ou renouvellement des jetons."""
    p = request.POST
    if request.content_type == "application/json":  # tolérance : la norme demande un formulaire
        try:
            p = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _erreur("invalid_request", "Corps illisible.")
    client_id = p.get("client_id", "")
    client = ClientOAuth.objects.filter(client_id=client_id).first() if client_id else None
    if client_id and not client:
        return _erreur("invalid_client", "Application inconnue.", 401)
    maintenant = timezone.now()
    grant = p.get("grant_type")

    if grant == "authorization_code":
        if not client:
            return _erreur("invalid_request", "client_id manquant.")
        code = CodeOAuth.objects.select_related("utilisateur").filter(code_hash=empreinte(p.get("code", ""))).first()
        if not code or code.client_id != client.id:
            return _erreur("invalid_grant", "Code inconnu ou déjà utilisé.")
        code.delete()  # usage unique, même si la suite échoue
        verificateur = p.get("code_verifier", "")
        if (code.expire_le < maintenant or p.get("redirect_uri", "") != code.redirect_uri
                or not 43 <= len(verificateur) <= 128
                or not secrets.compare_digest(_pkce(verificateur), code.code_challenge)
                or not code.utilisateur.is_active):
            return _erreur("invalid_grant", "Code expiré ou invalide.")
        return _emettre(None, client, code.utilisateur)

    if grant == "refresh_token":
        j = JetonOAuth.objects.select_related("client", "utilisateur").filter(
            rafraichissement_hash=empreinte(p.get("refresh_token", ""))).first()
        if (not j or (client and j.client_id != client.id) or j.rafraichissement_expire_le < maintenant
                or not j.utilisateur.is_active):
            return _erreur("invalid_grant", "Jeton de renouvellement invalide : reconnectez le connecteur.")
        return _emettre(j, j.client, j.utilisateur)

    return _erreur("unsupported_grant_type", "Types acceptés : authorization_code, refresh_token.")


# --------------------------------------------------------------------------- contrôle des appels /mcp

def utilisateur_du_jeton(request):
    """(utilisateur, jeton_fourni) : utilisateur None si l'accès est refusé."""
    entete = request.headers.get("Authorization", "")
    if not entete[:7].lower() == "bearer ":
        return None, False
    j = JetonOAuth.objects.select_related("utilisateur").filter(acces_hash=empreinte(entete[7:].strip())).first()
    maintenant = timezone.now()
    if not j or j.acces_expire_le < maintenant or not j.utilisateur.is_active:
        return None, True
    if not j.utilise_le or maintenant - j.utilise_le > datetime.timedelta(minutes=5):
        JetonOAuth.objects.filter(pk=j.pk).update(utilise_le=maintenant)
    return j.utilisateur, True


def refus(request, jeton_fourni):
    """401 qui indique à Claude où se connecter (et, si le jeton a expiré, qu'il doit le renouveler)."""
    r = JsonResponse({"error": "invalid_token" if jeton_fourni else "unauthorized",
                      "error_description": "Connexion à l'appli Menus famille nécessaire."}, status=401)
    entete = f'Bearer resource_metadata="{url_base(request)}/.well-known/oauth-protected-resource/mcp", scope="{PORTEE}"'
    if jeton_fourni:
        entete += ', error="invalid_token"'
    r["WWW-Authenticate"] = entete
    return r
