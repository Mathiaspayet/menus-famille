"""
Import et export du plan au format JSON (format décrit dans docs/FORMAT_PLAN.md).

Le même format sert dans les deux sens : on exporte l'état actuel, on le fait
modifier par Claude, on réimporte le fichier corrigé.
"""
import datetime

from django.db import transaction
from django.utils import timezone

from .models import Article, Jour, ListeCourses, PetitDej, Plan, Recette, ResteFrigo

VERSION = 1
MAGASINS = {code for code, _ in Article.MAGASINS}


class PlanInvalide(ValueError):
    """Le fichier ne respecte pas le format attendu (message en français)."""


def _date(valeur, contexte):
    try:
        return datetime.date.fromisoformat(valeur)
    except (TypeError, ValueError):
        raise PlanInvalide(f"Date invalide pour {contexte} : {valeur!r} (format attendu AAAA-MM-JJ).")


def _verifier(data):
    if not isinstance(data, dict):
        raise PlanInvalide("Le fichier doit contenir un objet JSON.")
    if data.get("version") != VERSION:
        raise PlanInvalide(f"Version de format inconnue : {data.get('version')!r} (attendu : {VERSION}).")
    for cle in ("recettes", "semaines", "listes"):
        if cle not in data:
            raise PlanInvalide(f"Clé obligatoire absente : « {cle} ».")
    recettes = data["recettes"]
    pdj = data.get("petits_dejeuners", {})
    for w in data["semaines"]:
        for d in w.get("days", []):
            jour = d.get("full") or d.get("iso")
            for champ in ("soir", "prep"):
                if d.get(champ) and d[champ] not in recettes:
                    raise PlanInvalide(f"{jour} : la recette « {d[champ]} » ({champ}) n'existe pas.")
            midi = d.get("midi") or {}
            if midi.get("r") and midi["r"] not in recettes:
                raise PlanInvalide(f"{jour} : la recette « {midi['r']} » (midi) n'existe pas.")
            if d.get("pdj") and d["pdj"] not in pdj:
                raise PlanInvalide(f"{jour} : la formule de petit-déjeuner « {d['pdj']} » n'existe pas.")
    for liste in data["listes"]:
        for magasin in liste.get("shops", {}):
            if magasin not in MAGASINS:
                raise PlanInvalide(f"Magasin inconnu « {magasin} » (attendus : {', '.join(sorted(MAGASINS))}).")


@transaction.atomic
def importer_plan(data, utilisateur=None):
    """Remplace le plan. Les cases cochées sont conservées pour les articles
    identiques (même date de courses, même magasin, même nom), sauf si le
    fichier indique lui-même l'état coché (6e élément de l'article).
    Renvoie un petit résumé (dict) pour l'affichage."""
    _verifier(data)

    anciens = {
        (a.liste.date_courses, a.magasin, a.nom): (a.coche, a.coche_par_id, a.coche_le)
        for a in Article.objects.select_related("liste").filter(coche=True)
    }

    Jour.objects.all().delete()
    ListeCourses.objects.all().delete()
    Recette.objects.all().delete()
    PetitDej.objects.all().delete()

    plan = Plan.actuel()
    plan.personnes = data.get("personnes", [])
    plan.debut = _date(data["debut"], "debut") if data.get("debut") else None
    plan.infos_html = data.get("infos_html", "")
    plan.importe_le = timezone.now()
    plan.save()

    recettes = {}
    for cle, r in data["recettes"].items():
        recettes[cle] = Recette.objects.create(
            cle=cle, titre=r.get("t", cle), duree=r.get("time") or "",
            boites=bool(r.get("boxes")), boite_prep=bool(r.get("box_prep")),
            feu=r.get("fire") or "", dessert=r.get("des") or "", note=r.get("note") or "",
            ingredients=r.get("ing") or [], etapes=r.get("steps") or [], portions=r.get("por") or [],
        )

    formules = {}
    for code, f in data.get("petits_dejeuners", {}).items():
        formules[code] = PetitDej.objects.create(
            code=code, titre=f.get("t", code), jours=f.get("days") or "",
            lignes=f.get("rows") or [], preparation=f.get("how") or "",
        )

    nb_jours = 0
    for w in data["semaines"]:
        for d in w.get("days", []):
            midi = d.get("midi") or {}
            Jour.objects.create(
                date=_date(d.get("iso"), d.get("full", "un jour")),
                semaine=w.get("n", 0), semaine_libelle=w.get("label", ""),
                libelle=d.get("full") or d["iso"], a_faire=d.get("todo") or [],
                petit_dej=formules.get(d.get("pdj")),
                midi_texte=midi.get("lbl") or "", midi_detail=midi.get("sub") or "",
                midi_recette=recettes.get(midi.get("r")), midi_boite=bool(midi.get("box")),
                gouter=d.get("gouter") or "",
                soir=recettes.get(d.get("soir")), a_preparer=recettes.get(d.get("prep")),
                remarque=d.get("remarque") or "",
            )
            nb_jours += 1

    nb_articles = 0
    for liste_data in data["listes"]:
        liste = ListeCourses.objects.create(
            libelle=liste_data.get("label", ""), periode=liste_data.get("range", ""),
            date_courses=_date(liste_data.get("shop"), liste_data.get("label", "une liste")),
        )
        for magasin, categories in liste_data.get("shops", {}).items():
            ordre = 0
            for cat in categories:
                for item in cat.get("items", []):
                    item = list(item) + [""] * (5 - len(item))
                    nom = item[0]
                    if len(item) >= 6 and item[5] is not None:  # état coché fourni par le fichier
                        coche, par, le = bool(item[5]), None, timezone.now() if item[5] else None
                    else:
                        coche, par, le = anciens.get((liste.date_courses, magasin, nom), (False, None, None))
                    # 7e élément facultatif : date du premier repas qui utilise l'article
                    pour_le = _date(item[6], f"l'article « {nom} »") if len(item) >= 7 and item[6] else None
                    Article.objects.create(
                        liste=liste, magasin=magasin, categorie=cat.get("c", ""), ordre=ordre,
                        nom=nom, quantite=item[1] or "", commentaire=item[2] or "",
                        congeler=bool(item[3]), verifier=bool(item[4]), pour_le=pour_le,
                        coche=coche, coche_par_id=par, coche_le=le,
                    )
                    ordre += 1
                    nb_articles += 1

    if "frigo" in data:  # le fichier décrit aussi le frigo : on le remplace
        ResteFrigo.objects.all().delete()
        for r in data["frigo"]:
            ResteFrigo.objects.create(nom=r.get("nom", ""), quantite=r.get("quantite", ""),
                                      remarque=r.get("remarque", ""), ajoute_par=utilisateur)

    return {"recettes": len(recettes), "jours": nb_jours, "listes": len(data["listes"]), "articles": nb_articles}


def exporter_plan():
    """Plan + état actuel (cases cochées, frigo, remarques) au format d'import."""
    plan = Plan.actuel()
    recettes = {
        r.cle: {"t": r.titre, "time": r.duree, "boxes": r.boites, "box_prep": r.boite_prep,
                "fire": r.feu or None, "des": r.dessert or None, "note": r.note or None,
                "ing": r.ingredients, "steps": r.etapes, "por": r.portions}
        for r in Recette.objects.all()
    }
    pdj = {f.code: {"t": f.titre, "days": f.jours, "rows": f.lignes, **({"how": f.preparation} if f.preparation else {})}
           for f in PetitDej.objects.all()}

    semaines = {}
    for j in Jour.objects.select_related("petit_dej", "midi_recette", "soir", "a_preparer"):
        s = semaines.setdefault(j.semaine, {"n": j.semaine, "label": j.semaine_libelle, "days": []})
        midi = {k: v for k, v in {"lbl": j.midi_texte, "sub": j.midi_detail,
                                  "r": j.midi_recette.cle if j.midi_recette else None,
                                  "box": j.midi_boite or None}.items() if v}
        jour = {"iso": j.date.isoformat(), "full": j.libelle, "todo": j.a_faire,
                "pdj": j.petit_dej.code if j.petit_dej else None, "midi": midi,
                "gouter": j.gouter or None, "soir": j.soir.cle if j.soir else None}
        if j.a_preparer:
            jour["prep"] = j.a_preparer.cle
        if j.remarque:
            jour["remarque"] = j.remarque
        s["days"].append(jour)

    listes = []
    for liste in ListeCourses.objects.prefetch_related("articles"):
        shops = {}
        for a in liste.articles.all():
            cats = shops.setdefault(a.magasin, [])
            if not cats or cats[-1]["c"] != a.categorie:
                cats.append({"c": a.categorie, "items": []})
            cats[-1]["items"].append([a.nom, a.quantite, a.commentaire, int(a.congeler), int(a.verifier), int(a.coche),
                                      a.pour_le.isoformat() if a.pour_le else None])
        listes.append({"label": liste.libelle, "shop": liste.date_courses.isoformat(), "range": liste.periode, "shops": shops})

    return {
        "version": VERSION,
        "exporte_le": timezone.localtime().isoformat(timespec="minutes"),
        "personnes": plan.personnes,
        "debut": plan.debut.isoformat() if plan.debut else None,
        "recettes": recettes,
        "petits_dejeuners": pdj,
        "semaines": [semaines[k] for k in sorted(semaines)],
        "listes": listes,
        "frigo": [{"nom": r.nom, "quantite": r.quantite, "remarque": r.remarque} for r in ResteFrigo.objects.all()],
        "infos_html": plan.infos_html,
    }
