"""
Serveur MCP (Model Context Protocol) de l'appli, à l'adresse /mcp.

Claude (web, ordinateur, téléphone, Claude Code) y envoie des messages
JSON-RPC en HTTP POST (transport « Streamable HTTP »). Ce serveur est sans
session et répond toujours en JSON simple, ce que la spécification autorise :
pas de flux SSE, donc rien de particulier à régler sur le proxy du NAS.

Chaque requête doit porter un jeton obtenu par la connexion OAuth (oauth.py) :
les outils agissent alors au nom de la personne qui a autorisé Claude.
"""
import json
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.http.request import validate_host
from django.views.decorators.csrf import csrf_exempt

from . import mcp_outils, oauth

journal = logging.getLogger(__name__)

# Versions du protocole comprises, de la plus récente à la plus ancienne.
VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]

INSTRUCTIONS = (
    "Appli « Menus famille » : menus de la semaine, recettes, listes de courses partagées entre les parents "
    "et restes au frigo. Commencer par lire_infos_famille (personnes, consignes, allergies), puis lire_semaine "
    "ou lire_jour. Dates au format AAAA-MM-JJ. Pour un plat nouveau : enregistrer_recette, puis modifier_jour. "
    "Après un changement de repas, proposer de mettre à jour la liste de courses concernée (lire_courses, "
    "ajouter_article / retirer_article, ou remplacer_liste_courses) et tenir compte du frigo (lire_frigo). "
    "Respecter les portions par personne et les consignes de l'onglet Infos. Les cases cochées sont partagées : "
    "ne pas les décocher sans demande. Annoncer clairement chaque modification faite."
)


def _origine_autorisee(origine, request):
    """Protection contre le « DNS rebinding » demandée par la spécification :
    un navigateur ne doit pas pouvoir appeler /mcp depuis un autre site."""
    hote = urlsplit(origine).hostname or ""
    return validate_host(hote, settings.ALLOWED_HOSTS) or hote == request.get_host().split(":")[0]


def _erreur(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _initialiser(params):
    demandee = params.get("protocolVersion")
    return {
        "protocolVersion": demandee if demandee in VERSIONS else VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "menus-famille", "title": "Menus famille", "version": settings.BUILD_VERSION[:12]},
        "instructions": INSTRUCTIONS,
    }


def _traiter(message, utilisateur):
    """Un message JSON-RPC → la réponse (dict), ou None pour une notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _erreur(None, -32600, "Requête JSON-RPC invalide.")
    methode, id_ = message.get("method"), message.get("id")
    if not isinstance(methode, str) or "id" not in message:
        return None  # notification (ex. notifications/initialized) ou réponse du client : rien à renvoyer
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _erreur(id_, -32602, "« params » doit être un objet.")
    try:
        if methode == "initialize":
            resultat = _initialiser(params)
        elif methode == "ping":
            resultat = {}
        elif methode == "tools/list":
            resultat = {"tools": mcp_outils.definitions()}
        elif methode == "tools/call":
            resultat = mcp_outils.appeler(params.get("name"), params.get("arguments") or {}, utilisateur)
        else:
            return _erreur(id_, -32601, f"Méthode non prise en charge : {methode}")
    except mcp_outils.OutilInconnu as e:
        return _erreur(id_, -32602, f"Outil inconnu : {e}")
    except Exception:
        journal.exception("Erreur MCP (%s)", methode)
        return _erreur(id_, -32603, "Erreur interne de l'appli.")
    return {"jsonrpc": "2.0", "id": id_, "result": resultat}


@csrf_exempt
def point_mcp(request):
    origine = request.headers.get("Origin")
    if origine and not _origine_autorisee(origine, request):
        return HttpResponse("Origine refusée", status=403, content_type="text/plain")

    utilisateur, jeton_fourni = oauth.utilisateur_du_jeton(request)
    if not utilisateur:
        return oauth.refus(request, jeton_fourni)

    if request.method != "POST":
        # Pas de flux d'événements (GET) ni de session à fermer (DELETE) : permis par la spécification.
        reponse = HttpResponse(status=405)
        reponse["Allow"] = "POST"
        return reponse

    try:
        message = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(_erreur(None, -32700, "JSON illisible."), status=400)

    if isinstance(message, list):  # lot de messages (version 2025-03-26)
        reponses = [r for r in (_traiter(m, utilisateur) for m in message) if r]
        return JsonResponse(reponses, safe=False) if reponses else HttpResponse(status=202)
    reponse = _traiter(message, utilisateur)
    return JsonResponse(reponse) if reponse else HttpResponse(status=202)
