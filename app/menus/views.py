"""Écrans de l'appli. Toutes les pages demandent d'être connecté, sauf /sante/."""
import datetime
import json
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Article, Jour, ListeCourses, PetitDej, Plan, ResteFrigo
from . import courses as courses_mod
from .plan_io import PlanInvalide, exporter_plan, importer_plan

MAGASINS = dict(Article.MAGASINS)
CONSEILS = {
    "boucher": "Demandez un sachet par viande et notez le jour dessus avant de congeler à plat.",
    "primeur": "Tout tient la semaine au bac à légumes. Les herbes se gardent dans un verre d'eau au frigo.",
    "leclerc": "« Vérifier » : lisez l'étiquette, ni « arachide » ni « traces d'arachide ».",
}


def lien_claude(question):
    """Bouton « Modifier avec Claude ».

    - Projet Claude configuré (CLAUDE_PROJECT_URL) : le bouton ouvre la page du
      projet ; claude.js copie la question dans le presse-papiers, à coller dans
      la zone de saisie du projet (nouvelle conversation dans le projet).
      Un lien de projet ne sait pas pré-remplir la question, et le paramètre
      « project » de claude.ai/new n'est pas fiable (ignoré par l'appli mobile).
    - Sinon : nouvelle conversation simple avec la question pré-remplie.
    """
    if settings.CLAUDE_PROJECT_URL:
        return {"url": settings.CLAUDE_PROJECT_URL, "question": question, "projet": True}
    return {"url": "https://claude.ai/new?q=" + quote(question), "question": question, "projet": False}


def service_worker(request):
    """Le service worker doit être servi à la racine pour couvrir toute l'appli."""
    reponse = render(request, "menus/sw.js", {"version": settings.BUILD_VERSION[:12]},
                     content_type="application/javascript; charset=utf-8")
    reponse["Cache-Control"] = "no-cache"
    reponse["Service-Worker-Allowed"] = "/"
    return reponse


def sante(request):
    """Sonde pour le healthcheck Docker (pas de connexion requise)."""
    return HttpResponse("ok", content_type="text/plain")


@login_required
def accueil(request):
    """Ouvre le jour d'aujourd'hui s'il est dans le plan, sinon le premier jour."""
    aujourdhui = timezone.localdate()
    jour = Jour.objects.filter(date=aujourdhui).first() or Jour.objects.filter(date__gt=aujourdhui).first() \
        or Jour.objects.first()
    if not jour:
        return redirect("plan")
    return redirect("jour", date=jour.date.isoformat())


@login_required
def jour(request, date):
    try:
        date = datetime.date.fromisoformat(date)
    except ValueError:
        raise Http404("Date invalide")
    j = get_object_or_404(Jour.objects.select_related("petit_dej", "midi_recette", "soir", "a_preparer"), date=date)
    # Bande des jours : tout le plan sur une ligne qu'on fait défiler du doigt.
    jours = list(Jour.objects.values("date", "semaine", "semaine_libelle"))
    for i, d in enumerate(jours):
        d["nouvelle_semaine"] = i > 0 and d["semaine"] != jours[i - 1]["semaine"]
    precedent = Jour.objects.filter(date__lt=j.date).last()
    suivant = Jour.objects.filter(date__gt=j.date).first()

    repas = [x for x in [j.midi_recette and j.midi_recette.titre, j.soir and j.soir.titre] if x]
    libelle = j.libelle.rstrip(".")
    question = (f"Menus famille — {libelle}. Prévu : " + " ; ".join(repas) + ". Je voudrais modifier : ") if repas \
        else f"Menus famille — {libelle}. Je voudrais modifier : "
    return render(request, "menus/jour.html", {
        "onglet": "jour", "j": j, "jours": jours, "precedent": precedent, "suivant": suivant,
        "aujourdhui": timezone.localdate(),
        "personnes": Plan.actuel().personnes, "lien_claude": lien_claude(question),
    })


@login_required
@require_POST
def jour_remarque(request, date):
    try:
        j = get_object_or_404(Jour, date=datetime.date.fromisoformat(date))
    except ValueError:
        raise Http404("Date invalide")
    j.remarque = request.POST.get("remarque", "").strip()
    j.save(update_fields=["remarque"])
    return redirect("jour", date=date)


@login_required
def petit_dej(request):
    return render(request, "menus/petit_dej.html", {
        "onglet": "plus", "formules": PetitDej.objects.all(), "personnes": Plan.actuel().personnes,
    })


@login_required
def courses(request, liste_id=None):
    """Une seule liste, tous les menus à venir, du plus urgent au moins urgent.
    (liste_id : anciennes adresses par liste, gardées pour ne pas casser les liens.)"""
    magasin = request.GET.get("magasin", "boucher")
    if magasin not in MAGASINS:
        magasin = "boucher"
    try:
        jours = int(request.GET.get("jours", courses_mod.HORIZON_PAR_DEFAUT))
    except ValueError:
        jours = courses_mod.HORIZON_PAR_DEFAUT
    if jours not in dict(courses_mod.HORIZONS):
        jours = courses_mod.HORIZON_PAR_DEFAUT
    aujourdhui = timezone.localdate()
    donnees = courses_mod.liste_globale(magasin, jours, aujourdhui)
    return render(request, "menus/courses.html", {
        "onglet": "courses", "magasin": magasin, "jours": jours, "horizons": courses_mod.HORIZONS,
        "aujourdhui": aujourdhui, "conseil": CONSEILS[magasin],
        "compteurs": [{"code": c, "nom": n, "nombre": donnees["a_acheter"][c]} for c, n in Article.MAGASINS],
        **donnees,
    })


@login_required
def courses_etat_global(request):
    """État de toutes les cases (et date d'usage) : la page le relit toutes les
    quelques secondes pour afficher ce que l'autre personne a coché."""
    return JsonResponse({"articles": {a.id: {"c": a.coche, "m": a.magasin, "d": a.prio.isoformat(),
                                             "k": courses_mod.cle(a)}
                                      for a in courses_mod.tous_les_articles()}})


@login_required
@require_POST
def article_cocher(request, article_id):
    """Appelé en arrière-plan quand on coche ou décoche une case."""
    a = get_object_or_404(Article, pk=article_id)
    try:
        coche = bool(json.loads(request.body or "{}").get("coche"))
    except json.JSONDecodeError:
        return JsonResponse({"erreur": "requête invalide"}, status=400)
    a.coche = coche
    a.coche_par = request.user if coche else None
    a.coche_le = timezone.now() if coche else None
    a.save(update_fields=["coche", "coche_par", "coche_le"])
    return JsonResponse({"id": a.id, "coche": a.coche})


@login_required
def courses_etat(request, liste_id):
    """État de toutes les cases d'une liste : la page l'interroge toutes les
    quelques secondes pour afficher ce que l'autre personne a coché."""
    liste = get_object_or_404(ListeCourses, pk=liste_id)
    return JsonResponse({"articles": {a.id: {"c": a.coche, "m": a.magasin} for a in liste.articles.all()}})


@login_required
@require_POST
def courses_decocher(request, liste_id):
    liste = get_object_or_404(ListeCourses, pk=liste_id)
    magasin = request.POST.get("magasin", "")
    liste.articles.filter(magasin=magasin).update(coche=False, coche_par=None, coche_le=None)
    return redirect(f"/courses/{liste.id}/?magasin={magasin}")


@login_required
def frigo(request):
    if request.method == "POST":
        nom = request.POST.get("nom", "").strip()
        if nom:
            ResteFrigo.objects.create(nom=nom, quantite=request.POST.get("quantite", "").strip(),
                                      remarque=request.POST.get("remarque", "").strip(), ajoute_par=request.user)
        return redirect("frigo")
    restes = ResteFrigo.objects.select_related("ajoute_par")
    texte = ", ".join(str(r) for r in restes) or "rien de particulier"
    question = f"Menus famille — il nous reste au frigo : {texte}. Peux-tu adapter les prochains repas pour les utiliser ?"
    return render(request, "menus/frigo.html", {"onglet": "frigo", "restes": restes, "lien_claude": lien_claude(question)})


@login_required
@require_POST
def frigo_retirer(request, reste_id):
    ResteFrigo.objects.filter(pk=reste_id).delete()
    return redirect("frigo")


@login_required
def plus(request):
    """Le reste de l'appli : petits-déjeuners, consignes, plan, compte, version."""
    return render(request, "menus/plus.html", {"onglet": "plus"})


@login_required
def infos(request):
    return render(request, "menus/infos.html", {"onglet": "plus", "plan": Plan.actuel()})


@login_required
def exporter(request):
    contenu = json.dumps(exporter_plan(), ensure_ascii=False, indent=1)
    nom = f"plan-menus-{timezone.localdate():%Y-%m-%d}.json"
    reponse = HttpResponse(contenu, content_type="application/json; charset=utf-8")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


@user_passes_test(lambda u: u.is_staff)
def plan(request):
    """Importer un nouveau plan (réservé aux comptes « équipe », ex. Mathias)."""
    if request.method == "POST":
        fichier = request.FILES.get("fichier")
        if not fichier:
            messages.error(request, "Choisissez un fichier JSON.")
        else:
            try:
                resume = importer_plan(json.load(fichier), utilisateur=request.user)
            except (json.JSONDecodeError, UnicodeDecodeError):
                messages.error(request, "Ce fichier n'est pas un JSON lisible.")
            except PlanInvalide as e:
                messages.error(request, f"Plan refusé : {e}")
            else:
                messages.success(request, "Plan importé : {recettes} recettes, {jours} jours, {listes} listes "
                                          "et {articles} articles. Les cases déjà cochées sont conservées.".format(**resume))
                return redirect("accueil")
    return render(request, "menus/plan.html", {"onglet": "plus", "plan": Plan.actuel(), "vide": not Jour.objects.exists()})
