"""
Outils proposés à Claude par le serveur MCP (voir mcp.py et docs/MCP.md).

Chaque outil est une fonction Python décorée par @outil : le décorateur
décrit l'outil à Claude (nom, explication, paramètres attendus) et la
fonction fait le travail dans la base. Ce qu'elle renvoie est transmis à
Claude en JSON ; une ErreurOutil lui est renvoyée comme message d'erreur
(il peut alors corriger et réessayer).

Rien de familial ici : les textes sont génériques, les données viennent de la base.
"""
import datetime
import json
import logging
import re

from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone
from django.utils.html import strip_tags

from .models import Article, Jour, ListeCourses, PetitDej, Plan, Recette, ResteFrigo
from .plan_io import PlanInvalide, exporter_plan, importer_plan

journal = logging.getLogger(__name__)

MAGASINS = dict(Article.MAGASINS)
CLE_RECETTE = re.compile(r"^[a-z0-9_-]{1,80}$")


class ErreurOutil(Exception):
    """Erreur expliquée à Claude (en français), qui peut corriger sa demande."""


class OutilInconnu(Exception):
    pass


OUTILS = {}

# Petits raccourcis pour écrire les paramètres attendus (JSON Schema).
TEXTE = {"type": "string"}
DATE = {"type": "string", "description": "Date au format AAAA-MM-JJ. Absente : aujourd'hui (ou le prochain jour du plan)."}
BOOLEEN = {"type": "boolean"}
LISTE_TEXTES = {"type": "array", "items": {"type": "string"}}
MAGASIN = {"type": "string", "enum": list(MAGASINS)}


def outil(nom, titre, description, proprietes=None, requis=(), lecture_seule=False, destructif=False):
    def decorer(fonction):
        OUTILS[nom] = ({
            "name": nom,
            "title": titre,
            "description": description,
            "inputSchema": {"type": "object", "properties": proprietes or {}, "required": list(requis),
                            "additionalProperties": False},
            "annotations": {"title": titre, "readOnlyHint": lecture_seule, "destructiveHint": destructif,
                            "openWorldHint": False},
        }, fonction)
        return fonction
    return decorer


def definitions():
    return [definition for definition, _ in OUTILS.values()]


_TYPES = {"string": str, "boolean": bool, "array": list, "object": dict}


def _verifier_arguments(definition, arguments):
    schema = definition["inputSchema"]
    if not isinstance(arguments, dict):
        raise ErreurOutil("Les arguments doivent être un objet JSON.")
    inconnus = set(arguments) - set(schema["properties"])
    if inconnus:
        raise ErreurOutil(f"Paramètre(s) inconnu(s) : {', '.join(sorted(inconnus))}.")
    manquants = [p for p in schema["required"] if arguments.get(p) is None]
    if manquants:
        raise ErreurOutil(f"Paramètre(s) obligatoire(s) manquant(s) : {', '.join(manquants)}.")
    for cle, valeur in arguments.items():
        attendu = schema["properties"][cle].get("type")
        if valeur is None:
            continue
        if attendu == "integer":
            ok = isinstance(valeur, int) and not isinstance(valeur, bool)
        else:
            ok = attendu not in _TYPES or isinstance(valeur, _TYPES[attendu])
            if attendu != "boolean" and isinstance(valeur, bool):
                ok = False
        if not ok:
            raise ErreurOutil(f"« {cle} » doit être de type {attendu}.")


def appeler(nom, arguments, utilisateur):
    """Exécute un outil et renvoie le résultat au format MCP (tools/call)."""
    if nom not in OUTILS:
        raise OutilInconnu(nom)
    definition, fonction = OUTILS[nom]
    try:
        _verifier_arguments(definition, arguments)
        with transaction.atomic():
            resultat = fonction(utilisateur, **{k: v for k, v in arguments.items() if v is not None})
    except ErreurOutil as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except Exception:
        journal.exception("Erreur dans l'outil MCP %s", nom)
        return {"content": [{"type": "text", "text": "Erreur interne de l'appli (voir le journal du conteneur)."}],
                "isError": True}
    texte = resultat if isinstance(resultat, str) else json.dumps(resultat, ensure_ascii=False)
    return {"content": [{"type": "text", "text": texte}], "isError": False}


# --------------------------------------------------------------------------- aides

def _date(valeur, champ="date"):
    if not valeur:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(valeur)
    except ValueError:
        raise ErreurOutil(f"{champ} : date invalide {valeur!r} (format attendu AAAA-MM-JJ).")


def _quand(dt):
    return timezone.localtime(dt).isoformat(timespec="minutes") if dt else None


def _nom(u):
    return (u.first_name or u.username) if u else None


def _plage_du_plan():
    premier, dernier = Jour.objects.first(), Jour.objects.last()
    if not premier:
        return "le plan est vide (aucun jour importé)"
    return f"le plan va du {premier.date.isoformat()} au {dernier.date.isoformat()}"


JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _jour(date, au_plus_proche=False):
    """Le jour demandé. Sans date précise (au_plus_proche) : aujourd'hui, sinon le
    prochain jour du plan, sinon le premier — comme la page d'accueil."""
    jours = Jour.objects.select_related("petit_dej", "midi_recette", "soir", "a_preparer")
    j = jours.filter(date=date).first()
    if not j and au_plus_proche:
        j = jours.filter(date__gt=date).first() or jours.first()
    if not j:
        raise ErreurOutil(f"Aucun jour {date.isoformat()} dans le plan : {_plage_du_plan()}.")
    return j


def _recette(cle, champ="recette"):
    r = Recette.objects.filter(cle=cle).first()
    if not r:
        raise ErreurOutil(f"{champ} : la recette « {cle} » n'existe pas. Voir lister_recettes, "
                          "ou la créer avec enregistrer_recette.")
    return r


def _recette_courte(r):
    return {"cle": r.cle, "titre": r.titre, "duree": r.duree} if r else None


def _recette_complete(r):
    if not r:
        return None
    return {"cle": r.cle, "titre": r.titre, "duree": r.duree, "boites": r.boites, "boite_prep": r.boite_prep,
            "feu": r.feu, "dessert": r.dessert, "note": r.note, "ingredients": r.ingredients,
            "etapes": r.etapes, "portions": r.portions}


def _formule(f):
    return {"code": f.code, "titre": f.titre, "jours": f.jours, "lignes": f.lignes,
            "preparation": f.preparation} if f else None


def _jour_resume(j):
    return {
        "date": j.date.isoformat(), "libelle": j.libelle,
        "petit_dej": f"{j.petit_dej.code} · {j.petit_dej.titre}" if j.petit_dej else None,
        "midi": {"texte": j.midi_texte, "detail": j.midi_detail, "boite": j.midi_boite,
                 "recette": _recette_courte(j.midi_recette)},
        "gouter": j.gouter, "soir": _recette_courte(j.soir), "a_preparer": _recette_courte(j.a_preparer),
        "a_faire": j.a_faire, "remarque": j.remarque,
    }


def _liste(date_courses):
    if date_courses:
        liste = ListeCourses.objects.filter(date_courses=_date(date_courses, "date_courses")).first()
        if not liste:
            dates = ", ".join(l.date_courses.isoformat() for l in ListeCourses.objects.all()) or "aucune"
            raise ErreurOutil(f"Pas de liste de courses le {date_courses}. Listes existantes : {dates}.")
        return liste
    aujourdhui = timezone.localdate()
    liste = ListeCourses.objects.filter(date_courses__lte=aujourdhui).last() or ListeCourses.objects.first()
    if not liste:
        raise ErreurOutil("Aucune liste de courses dans le plan.")
    return liste


def _article(a):
    return {"id": a.id, "nom": a.nom, "quantite": a.quantite, "commentaire": a.commentaire,
            "congeler": a.congeler, "verifier": a.verifier, "coche": a.coche,
            "coche_par": _nom(a.coche_par), "coche_le": _quand(a.coche_le)}


def _textes(valeur, champ):
    if not isinstance(valeur, list) or not all(isinstance(x, str) for x in valeur):
        raise ErreurOutil(f"« {champ} » doit être une liste de textes.")
    return [x.strip() for x in valeur if x.strip()]


def _magasin(code):
    if code not in MAGASINS:
        raise ErreurOutil(f"Magasin inconnu « {code} » (attendus : {', '.join(MAGASINS)}).")
    return code


# --------------------------------------------------------------------------- lecture

@outil("lire_infos_famille", "Lire les infos de la famille",
       "Point de départ : personnes (ordre des colonnes des portions), consignes de la famille (onglet Infos : "
       "objectifs, allergies, règles), formules de petit-déjeuner, semaines et listes de courses disponibles, "
       "date du jour. À lire avant de proposer ou de modifier des repas.",
       lecture_seule=True)
def lire_infos_famille(utilisateur):
    plan = Plan.actuel()
    semaines = []
    for s in Jour.objects.values("semaine", "semaine_libelle").distinct().order_by("semaine"):
        jours = Jour.objects.filter(semaine=s["semaine"])
        semaines.append({"numero": s["semaine"], "libelle": s["semaine_libelle"],
                         "du": jours.first().date.isoformat(), "au": jours.last().date.isoformat()})
    aujourdhui = timezone.localdate()
    return {
        "aujourdhui": aujourdhui.isoformat(), "jour_de_la_semaine": JOURS_SEMAINE[aujourdhui.weekday()],
        "vous_parlez_a": _nom(utilisateur),
        "personnes": plan.personnes,
        "plan_importe_le": _quand(plan.importe_le),
        "infos": re.sub(r"\n\s*\n+", "\n", strip_tags(plan.infos_html)).strip(),
        "infos_html": plan.infos_html,
        "petits_dejeuners": [_formule(f) for f in PetitDej.objects.all()],
        "semaines": semaines,
        "listes_de_courses": [{"date_courses": l.date_courses.isoformat(), "libelle": l.libelle, "periode": l.periode}
                              for l in ListeCourses.objects.all()],
        "magasins": MAGASINS,
        "nombre_de_recettes": Recette.objects.count(),
    }


@outil("lire_semaine", "Lire une semaine de menus",
       "Les repas de chaque jour de la semaine qui contient la date (résumé : titres et clés des recettes).",
       {"date": DATE}, lecture_seule=True)
def lire_semaine(utilisateur, date=None):
    j = _jour(_date(date), au_plus_proche=not date)
    jours = Jour.objects.select_related("petit_dej", "midi_recette", "soir", "a_preparer").filter(semaine=j.semaine)
    return {"semaine": j.semaine, "libelle": j.semaine_libelle, "jours": [_jour_resume(x) for x in jours]}


@outil("lire_jour", "Lire le menu d'un jour",
       "Le détail d'un jour : à faire, petit-déjeuner, midi, goûter, soir et plat à préparer pour le lendemain, "
       "avec les recettes complètes (ingrédients, étapes, portions par personne) et la remarque du jour.",
       {"date": DATE}, lecture_seule=True)
def lire_jour(utilisateur, date=None):
    j = _jour(_date(date), au_plus_proche=not date)
    return {
        "date": j.date.isoformat(), "libelle": j.libelle, "semaine": j.semaine,
        "personnes": Plan.actuel().personnes,
        "a_faire": j.a_faire, "remarque": j.remarque,
        "petit_dej": _formule(j.petit_dej),
        "midi": {"texte": j.midi_texte, "detail": j.midi_detail, "boite": j.midi_boite,
                 "recette": _recette_complete(j.midi_recette)},
        "gouter": j.gouter,
        "soir": _recette_complete(j.soir),
        "a_preparer": _recette_complete(j.a_preparer),
    }


@outil("lister_recettes", "Lister les recettes",
       "Toutes les recettes du plan (clé, titre, durée) et les jours où chacune est prévue.", lecture_seule=True)
def lister_recettes(utilisateur):
    jours = {}
    for j in Jour.objects.all():
        for champ, cle in (("midi", j.midi_recette_id), ("soir", j.soir_id), ("a_preparer", j.a_preparer_id)):
            if cle:
                jours.setdefault(cle, []).append(f"{j.date.isoformat()} ({champ})")
    return [{"cle": r.cle, "titre": r.titre, "duree": r.duree, "boites": r.boites, "prevue": jours.get(r.id, [])}
            for r in Recette.objects.all()]


@outil("lire_recette", "Lire une recette", "Une recette complète, par sa clé.",
       {"cle": TEXTE}, requis=["cle"], lecture_seule=True)
def lire_recette(utilisateur, cle):
    return _recette_complete(_recette(cle))


@outil("lire_courses", "Lire une liste de courses",
       "Une liste de courses, par magasin et par rayon, avec l'identifiant de chaque article et ce qui est déjà "
       "coché (et par qui). Sans date : la liste en cours.",
       {"date_courses": {**DATE, "description": "Date des courses (AAAA-MM-JJ). Absente : la liste en cours."},
        "magasin": MAGASIN}, lecture_seule=True)
def lire_courses(utilisateur, date_courses=None, magasin=None):
    liste = _liste(date_courses)
    if magasin:
        _magasin(magasin)
    magasins = {}
    for a in liste.articles.select_related("coche_par"):
        if magasin and a.magasin != magasin:
            continue
        m = magasins.setdefault(a.magasin, {"nom": MAGASINS[a.magasin], "faits": 0, "total": 0, "rayons": []})
        m["total"] += 1
        m["faits"] += a.coche
        if not m["rayons"] or m["rayons"][-1]["rayon"] != a.categorie:
            m["rayons"].append({"rayon": a.categorie, "articles": []})
        m["rayons"][-1]["articles"].append(_article(a))
    return {"date_courses": liste.date_courses.isoformat(), "libelle": liste.libelle, "periode": liste.periode,
            "magasins": magasins,
            "autres_listes": [l.date_courses.isoformat() for l in ListeCourses.objects.exclude(pk=liste.pk)]}


@outil("lire_frigo", "Lire le frigo", "Les restes notés au frigo (à utiliser en priorité dans les prochains repas).",
       lecture_seule=True)
def lire_frigo(utilisateur):
    return [{"id": r.id, "nom": r.nom, "quantite": r.quantite, "remarque": r.remarque,
             "ajoute_le": _quand(r.ajoute_le), "ajoute_par": _nom(r.ajoute_par)}
            for r in ResteFrigo.objects.select_related("ajoute_par")]


@outil("exporter_plan_complet", "Exporter le plan complet",
       "Tout le plan au format d'import (recettes, semaines, listes, frigo, infos), comme le bouton "
       "« Télécharger le plan ». Volumineux : préférer les autres outils pour une petite modification.",
       lecture_seule=True)
def exporter_plan_complet(utilisateur):
    return exporter_plan()


# --------------------------------------------------------------------------- modification des menus

MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _libelle_jour(d):
    """Ex. « Lundi 16 nov. », comme dans les plans importés."""
    return f"{JOURS_SEMAINE[d.weekday()].capitalize()} {d.day} {MOIS_COURTS[d.month - 1]}"


_RECETTE = {"type": "object", "properties": {
    "cle": {"type": "string", "description": "Identifiant court : minuscules, chiffres, _ ou -. Ex. curry_poulet"},
    "titre": TEXTE, "duree": {"type": "string", "description": "Ex. 25 min"},
    "ingredients": LISTE_TEXTES, "etapes": LISTE_TEXTES,
    "portions": {"type": "array", "items": LISTE_TEXTES,
                 "description": "Une ligne par aliment : [aliment, part de la 1re personne, part de la 2e, ...]. Valeurs simples (« 120 g », « 1 pavé », « ⅗ de pavé ») : l'appli s'en sert pour recalculer les ingrédients quand quelqu'un est absent. Ingrédients commençant par la quantité (« 625 g de poulet »). Parts des boîtes du lendemain éventuellement sur des lignes « Boîte de demain : porc cru »."},
    "dessert": TEXTE, "note": TEXTE, "feu": {"type": "string", "description": "Pot du feu (piment à table)"},
    "boites": {"type": "boolean", "description": "Cuisiner 2 parts de plus pour les boîtes du lendemain"},
    "boite_prep": {"type": "boolean", "description": "Recette de boîte préparée la veille"}},
    "required": ["cle", "titre", "ingredients", "etapes"]}


def _enregistrer_une_recette(r, personnes, n):
    if not isinstance(r, dict):
        raise ErreurOutil(f"recettes[{n}] : un objet est attendu.")
    cle = str(r.get("cle") or "")
    if not CLE_RECETTE.match(cle):
        raise ErreurOutil(f"recettes[{n}].cle {cle!r} : uniquement minuscules sans accent, chiffres, _ ou -.")
    if not str(r.get("titre") or "").strip():
        raise ErreurOutil(f"recette {cle} : titre manquant.")
    portions = r.get("portions") or []
    for ligne in portions:
        if not isinstance(ligne, list) or not all(isinstance(x, str) for x in ligne):
            raise ErreurOutil(f"recette {cle} : chaque ligne de portions est une liste de textes [aliment, part 1, ...].")
        if personnes and len(ligne) != len(personnes) + 1:
            raise ErreurOutil(f"recette {cle} : chaque ligne de portions doit avoir {len(personnes) + 1} éléments "
                              f"(l'aliment puis une part pour : {', '.join(personnes)}).")
    _, cree = Recette.objects.update_or_create(cle=cle, defaults={
        "titre": str(r["titre"]).strip(), "duree": str(r.get("duree") or ""),
        "ingredients": _textes(r.get("ingredients") or [], f"{cle}.ingredients"),
        "etapes": _textes(r.get("etapes") or [], f"{cle}.etapes"), "portions": portions,
        "dessert": str(r.get("dessert") or ""), "note": str(r.get("note") or ""), "feu": str(r.get("feu") or ""),
        "boites": bool(r.get("boites")), "boite_prep": bool(r.get("boite_prep"))})
    return cree


@outil("enregistrer_recettes", "Créer ou modifier des recettes",
       "Enregistre une ou plusieurs recettes (10 au plus par appel) : création si la clé est nouvelle, sinon "
       "remplacement. Pour un nouveau plat : l'enregistrer ici, puis le placer avec modifier_jour ou "
       "enregistrer_semaine. Les portions suivent l'ordre de « personnes » (lire_infos_famille).",
       {"recettes": {"type": "array", "items": _RECETTE}}, requis=["recettes"])
def enregistrer_recettes(utilisateur, recettes):
    if not recettes:
        raise ErreurOutil("recettes : liste vide.")
    if len(recettes) > 15:
        raise ErreurOutil("15 recettes au plus par appel : découpez en plusieurs lots.")
    personnes = Plan.actuel().personnes
    creees = sum(_enregistrer_une_recette(r, personnes, n) for n, r in enumerate(recettes))
    return {"resultat": f"{creees} recette(s) créée(s), {len(recettes) - creees} remplacée(s)",
            "cles": [r["cle"] for r in recettes]}


_CHAMPS_JOUR = {
    "soir": {"type": "string", "description": "Clé de la recette du soir (\"\" pour vider)."},
    "midi_recette": {"type": "string", "description": "Clé de la recette du midi (\"\" pour vider)."},
    "midi_texte": {"type": "string", "description": "Texte du midi, ex. « Repas habituel » ou « Boîte : … »."},
    "midi_detail": {"type": "string", "description": "Précision sous le midi, ex. « Enfants à la cantine »."},
    "midi_boite": {"type": "boolean", "description": "Midi en boîte : la carte affiche le texte et la recette en détail."},
    "gouter": TEXTE,
    "a_preparer": {"type": "string", "description": "Clé de la recette à préparer ce soir pour le lendemain (\"\" pour vider)."},
    "petit_dej": {"type": "string", "description": "Code de la formule de petit-déjeuner (\"\" pour vider)."},
    "a_faire": {**LISTE_TEXTES, "description": "Liste « À faire » du jour (remplace l'ancienne)."},
    "remarque": {"type": "string", "description": "Note libre : repas sauté, invités… (\"\" pour effacer)."},
}
_TYPES_JOUR = {"midi_boite": bool, "a_faire": list}


def _appliquer_champs_jour(j, champs, contexte):
    for champ, valeur in champs.items():
        attendu = _TYPES_JOUR.get(champ, str)
        if champ not in _CHAMPS_JOUR or not isinstance(valeur, attendu):
            raise ErreurOutil(f"{contexte} : champ « {champ} » inconnu ou de mauvais type.")
    for champ in ("soir", "midi_recette", "a_preparer"):
        if champ in champs:
            setattr(j, champ, _recette(champs[champ], f"{contexte}, {champ}") if champs[champ] else None)
    if "petit_dej" in champs:
        code = champs["petit_dej"]
        j.petit_dej = PetitDej.objects.filter(code=code).first() if code else None
        if code and not j.petit_dej:
            codes = ", ".join(PetitDej.objects.values_list("code", flat=True)) or "aucune"
            raise ErreurOutil(f"{contexte} : formule de petit-déjeuner « {code} » inconnue (formules : {codes}). "
                              "La créer avec enregistrer_petits_dejeuners.")
    for champ in ("midi_texte", "midi_detail", "gouter", "remarque"):
        if champ in champs:
            setattr(j, champ, champs[champ].strip())
    if "midi_boite" in champs:
        j.midi_boite = champs["midi_boite"]
    if "a_faire" in champs:
        j.a_faire = _textes(champs["a_faire"], f"{contexte}, a_faire")


@outil("modifier_jour", "Modifier un jour (remplacer un repas)",
       "Change un ou plusieurs éléments d'un jour existant ; les champs absents ne bougent pas. Les repas désignent "
       "des recettes par leur clé (lister_recettes) : pour un plat nouveau, le créer d'abord avec "
       "enregistrer_recettes. Pensez ensuite à la liste de courses (lire_courses) et au « À faire » "
       "(ex. décongélation). Pour créer des jours, utiliser enregistrer_semaine.",
       {"date": {"type": "string", "description": "Date du jour à modifier (AAAA-MM-JJ)."}, **_CHAMPS_JOUR},
       requis=["date"])
def modifier_jour(utilisateur, date, **champs):
    j = _jour(_date(date))
    if not champs:
        raise ErreurOutil(f"Rien à modifier : indiquez au moins un champ parmi {', '.join(_CHAMPS_JOUR)}.")
    _appliquer_champs_jour(j, champs, j.libelle)
    j.save()
    return {"resultat": f"{j.libelle} modifié ({', '.join(champs)})", "jour": _jour_resume(j)}


_JOUR = {"type": "object", "properties": {
    "date": {"type": "string", "description": "AAAA-MM-JJ"},
    "libelle": {"type": "string", "description": "Ex. « Lundi 16 nov. » (calculé si absent)."}, **_CHAMPS_JOUR},
    "required": ["date"]}


@outil("enregistrer_semaine", "Créer ou mettre à jour une semaine",
       "Crée les jours qui n'existent pas et met à jour les autres (champs absents inchangés). Sert à préparer une "
       "nouvelle semaine ou à recopier un plan. Une semaine (7 jours au plus) par appel. Les recettes et formules "
       "de petit-déjeuner citées doivent déjà exister (enregistrer_recettes, enregistrer_petits_dejeuners). "
       "Penser ensuite à la liste de courses (remplacer_liste_courses).",
       {"numero": {"type": "integer", "description": "Numéro de la semaine dans le plan (1, 2, 3…)."},
        "libelle": {"type": "string", "description": "Ex. « 16 – 22 nov. »"},
        "jours": {"type": "array", "items": _JOUR}},
       requis=["numero", "jours"])
def enregistrer_semaine(utilisateur, numero, jours, libelle=None):
    if not jours or len(jours) > 7:
        raise ErreurOutil("jours : de 1 à 7 jours par appel (une semaine).")
    crees, resumes = 0, []
    for n, d in enumerate(jours):
        if not isinstance(d, dict) or not d.get("date"):
            raise ErreurOutil(f"jours[{n}] : un objet avec une « date » est attendu.")
        date = _date(d["date"], f"jours[{n}].date")
        j = Jour.objects.filter(date=date).first()
        if not j:
            j = Jour(date=date, semaine=numero, libelle=_libelle_jour(date))
            crees += 1
        j.semaine = numero
        if libelle is not None:
            j.semaine_libelle = libelle
        if d.get("libelle"):
            j.libelle = d["libelle"].strip()
        _appliquer_champs_jour(j, {k: v for k, v in d.items() if k not in ("date", "libelle") and v is not None},
                               j.libelle)
        j.save()
        resumes.append(f"{j.libelle} : {j.soir.titre if j.soir else '(pas de soir)'}")
    plan = Plan.actuel()
    premier = Jour.objects.first()
    if premier and plan.debut != premier.date:
        plan.debut = premier.date
        plan.save(update_fields=["debut"])
    return {"resultat": f"Semaine {numero} : {crees} jour(s) créé(s), {len(jours) - crees} mis à jour",
            "soirs": resumes}


@outil("supprimer_jours", "Supprimer des jours du plan",
       "Supprime les jours compris entre deux dates (incluses), par exemple une semaine passée ou annulée. "
       "Les recettes et les listes de courses ne sont pas touchées.",
       {"du": {"type": "string", "description": "AAAA-MM-JJ"}, "au": {"type": "string", "description": "AAAA-MM-JJ"}},
       requis=["du", "au"], destructif=True)
def supprimer_jours(utilisateur, du, au):
    debut, fin = _date(du, "du"), _date(au, "au")
    if fin < debut:
        raise ErreurOutil("« au » doit être après « du ».")
    n, _ = Jour.objects.filter(date__gte=debut, date__lte=fin).delete()
    return {"resultat": f"{n} jour(s) supprimé(s) du {debut.isoformat()} au {fin.isoformat()}"}


_FORMULE = {"type": "object", "properties": {
    "code": {"type": "string", "description": "Une lettre ou un code court, ex. A"},
    "titre": TEXTE, "jours": {"type": "string", "description": "Ex. « mardi et vendredi »"},
    "lignes": {"type": "array", "items": LISTE_TEXTES,
               "description": "[aliment, part de la 1re personne, part de la 2e, ...]"},
    "preparation": TEXTE}, "required": ["code", "titre", "lignes"]}


@outil("enregistrer_petits_dejeuners", "Créer ou modifier des formules de petit-déjeuner",
       "Enregistre une ou plusieurs formules (création si le code est nouveau, sinon remplacement).",
       {"formules": {"type": "array", "items": _FORMULE}}, requis=["formules"])
def enregistrer_petits_dejeuners(utilisateur, formules):
    if not formules:
        raise ErreurOutil("formules : liste vide.")
    codes = []
    for n, f in enumerate(formules):
        if not isinstance(f, dict) or not str(f.get("code") or "").strip() or len(str(f["code"]).strip()) > 4:
            raise ErreurOutil(f"formules[{n}] : « code » obligatoire (4 caractères au plus).")
        lignes = f.get("lignes") or []
        if not isinstance(lignes, list) or not all(isinstance(l, list) for l in lignes):
            raise ErreurOutil(f"formule {f['code']} : « lignes » est une liste de lignes [aliment, parts…].")
        code = str(f["code"]).strip()
        PetitDej.objects.update_or_create(code=code, defaults={
            "titre": str(f.get("titre") or code), "jours": str(f.get("jours") or ""), "lignes": lignes,
            "preparation": str(f.get("preparation") or "")})
        codes.append(code)
    return {"resultat": f"Formule(s) enregistrée(s) : {', '.join(codes)}"}


def _texte_en_html(texte):
    """Texte simple → cartes de l'onglet Infos : « ## Titre » ouvre une carte, « - » fait une liste."""
    from django.utils.html import escape
    cartes, liste = [], False
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if liste and not ligne.startswith("- "):
            cartes[-1] += "</ul>"
            liste = False
        if not ligne:
            continue
        if ligne.startswith("#"):
            cartes.append(f'<div class="card"><h3>{escape(ligne.lstrip("#").strip())}</h3>')
            continue
        if not cartes:
            cartes.append('<div class="card">')
        if ligne.startswith("- "):
            if not liste:
                cartes[-1] += '<ul class="rules">'
                liste = True
            cartes[-1] += f"<li>{escape(ligne[2:])}</li>"
        else:
            cartes[-1] += f"<p>{escape(ligne)}</p>"
    if liste:
        cartes[-1] += "</ul>"
    return "".join(c + "</div>" for c in cartes)


@outil("modifier_infos_famille", "Modifier les personnes et les consignes",
       "Change l'ordre des personnes (colonnes des portions) et/ou le contenu de l'onglet Infos (principe, "
       "allergies, repères de portions…). « infos » : texte simple (« ## Titre » pour une rubrique, « - » pour une "
       "puce) ou HTML. Remplace l'onglet en entier : partir de lire_infos_famille pour ne rien perdre. "
       "Réservé aux comptes « équipe ».",
       {"personnes": {**LISTE_TEXTES, "description": "Ex. [\"Parent 1\", \"Parent 2\", \"Enfant 1\", \"Enfant 2\"]"},
        "infos": TEXTE})
def modifier_infos_famille(utilisateur, personnes=None, infos=None):
    if not utilisateur.is_staff:
        raise ErreurOutil("Seul un compte « équipe » peut modifier les personnes et les consignes.")
    if personnes is None and infos is None:
        raise ErreurOutil("Indiquez « personnes » et/ou « infos ».")
    plan = Plan.actuel()
    if personnes is not None:
        plan.personnes = _textes(personnes, "personnes")
    if infos is not None:
        plan.infos_html = infos if re.search(r"<\w+[^>]*>", infos) else _texte_en_html(infos)
    plan.save()
    return {"resultat": "Infos de la famille mises à jour", "personnes": plan.personnes}


# --------------------------------------------------------------------------- courses

@outil("cocher_articles", "Cocher ou décocher des articles",
       "Coche (ou décoche, avec coche=false) des articles de courses par leur identifiant (lire_courses). "
       "Les cases sont partagées entre les parents : ne décocher que sur demande.",
       {"ids": {"type": "array", "items": {"type": "integer"}, "description": "Identifiants des articles."},
        "coche": {"type": "boolean", "description": "true pour cocher (par défaut), false pour décocher."}},
       requis=["ids"])
def cocher_articles(utilisateur, ids, coche=True):
    if not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ErreurOutil("ids : liste d'identifiants (nombres entiers) attendue.")
    articles = list(Article.objects.filter(pk__in=ids))
    absents = sorted(set(ids) - {a.id for a in articles})
    if absents:
        raise ErreurOutil(f"Article(s) introuvable(s) : {', '.join(map(str, absents))}. Relire la liste (lire_courses).")
    maintenant = timezone.now()
    for a in articles:
        a.coche, a.coche_par, a.coche_le = coche, (utilisateur if coche else None), (maintenant if coche else None)
        a.save(update_fields=["coche", "coche_par", "coche_le"])
    return {"resultat": f"{len(articles)} article(s) {'coché' if coche else 'décoché'}(s)",
            "articles": [f"{a.nom} ({MAGASINS[a.magasin]})" for a in articles]}


@outil("ajouter_article", "Ajouter un article à une liste de courses",
       "Ajoute un article dans une liste existante, à la fin de son rayon (créé s'il n'existe pas).",
       {"date_courses": {"type": "string", "description": "Date de la liste (AAAA-MM-JJ)."}, "magasin": MAGASIN,
        "nom": TEXTE, "quantite": TEXTE, "rayon": {"type": "string", "description": "Ex. Fruits, Volaille, Épicerie"},
        "commentaire": TEXTE, "congeler": BOOLEEN,
        "verifier": {"type": "boolean", "description": "Lire l'étiquette (allergène)."}},
       requis=["date_courses", "magasin", "nom"])
def ajouter_article(utilisateur, date_courses, magasin, nom, quantite="", rayon="Divers", commentaire="",
                    congeler=False, verifier=False):
    liste = _liste(date_courses)
    _magasin(magasin)
    rayon = rayon.strip() or "Divers"
    du_magasin = liste.articles.filter(magasin=magasin)
    dernier = du_magasin.filter(categorie=rayon).order_by("-ordre").first()
    if dernier:  # juste après le dernier article du même rayon
        ordre = dernier.ordre + 1
        du_magasin.filter(ordre__gte=ordre).update(ordre=F("ordre") + 1)
    else:
        ordre = (du_magasin.aggregate(m=Max("ordre"))["m"] or 0) + 1
    a = Article.objects.create(liste=liste, magasin=magasin, categorie=rayon, ordre=ordre, nom=nom.strip(),
                               quantite=quantite, commentaire=commentaire, congeler=congeler, verifier=verifier)
    return {"resultat": f"« {a.nom} » ajouté ({MAGASINS[magasin]}, {rayon})", "article": _article(a)}


@outil("retirer_article", "Retirer un article d'une liste de courses", "Supprime un article par son identifiant.",
       {"id": {"type": "integer"}}, requis=["id"], destructif=True)
def retirer_article(utilisateur, id):
    a = Article.objects.filter(pk=id).first()
    if not a:
        raise ErreurOutil(f"Article {id} introuvable.")
    a.delete()
    return {"resultat": f"« {a.nom} » retiré de la liste du {a.liste.libelle}"}


_ARTICLE = {"type": "object", "properties": {
    "nom": TEXTE, "quantite": TEXTE, "commentaire": TEXTE, "congeler": BOOLEEN, "verifier": BOOLEEN},
    "required": ["nom"]}
_RAYONS = {"type": "array", "items": {"type": "object", "properties": {
    "rayon": TEXTE, "articles": {"type": "array", "items": _ARTICLE}}, "required": ["rayon", "articles"]}}


@outil("remplacer_liste_courses", "Créer ou régénérer une liste de courses",
       "Remplace tous les articles de la liste de cette date (ou crée la liste). À utiliser après un changement de "
       "menus : recalculer les quantités à partir des recettes des jours couverts, regroupées par magasin et par rayon. "
       "Les articles déjà cochés (même magasin, même nom) restent cochés.",
       {"date_courses": {"type": "string", "description": "Date des courses (AAAA-MM-JJ)."},
        "libelle": {"type": "string", "description": "Ex. « Mar. 24 nov. » (obligatoire pour une nouvelle liste)."},
        "periode": {"type": "string", "description": "Repas couverts, ex. « du mar. 24 nov. soir au lun. 30 nov. »"},
        "magasins": {"type": "object", "properties": {code: _RAYONS for code in MAGASINS}, "additionalProperties": False,
                     "description": "Pour chaque magasin, la liste des rayons et de leurs articles."}},
       requis=["date_courses", "magasins"], destructif=True)
def remplacer_liste_courses(utilisateur, date_courses, magasins, libelle=None, periode=None):
    d = _date(date_courses, "date_courses")
    liste = ListeCourses.objects.filter(date_courses=d).first()
    if not liste and not libelle:
        raise ErreurOutil("libelle obligatoire pour créer une nouvelle liste (ex. « Mar. 24 nov. »).")
    for code in magasins:
        _magasin(code)
    cochees = {}
    if liste:
        cochees = {(a.magasin, a.nom.lower()): (a.coche_par_id, a.coche_le) for a in liste.articles.filter(coche=True)}
        liste.articles.all().delete()
        if libelle:
            liste.libelle = libelle
        if periode is not None:
            liste.periode = periode
        liste.save()
    else:
        liste = ListeCourses.objects.create(date_courses=d, libelle=libelle, periode=periode or "")
    total, gardes = 0, 0
    for code, rayons in magasins.items():
        if not isinstance(rayons, list):
            raise ErreurOutil(f"magasins.{code} : liste de rayons attendue.")
        ordre = 0
        for r in rayons:
            if not isinstance(r, dict) or not isinstance(r.get("articles"), list):
                raise ErreurOutil(f"magasins.{code} : chaque rayon est {{\"rayon\": ..., \"articles\": [...]}}.")
            for item in r["articles"]:
                if not isinstance(item, dict) or not str(item.get("nom") or "").strip():
                    raise ErreurOutil(f"magasins.{code} : chaque article doit avoir un « nom ».")
                nom = str(item["nom"]).strip()
                coche = cochees.get((code, nom.lower()))
                Article.objects.create(
                    liste=liste, magasin=code, categorie=str(r.get("rayon") or ""), ordre=ordre, nom=nom,
                    quantite=str(item.get("quantite") or ""), commentaire=str(item.get("commentaire") or ""),
                    congeler=bool(item.get("congeler")), verifier=bool(item.get("verifier")),
                    coche=bool(coche), coche_par_id=coche[0] if coche else None, coche_le=coche[1] if coche else None)
                ordre += 1
                total += 1
                gardes += bool(coche)
    return {"resultat": f"Liste du {liste.libelle} : {total} article(s), dont {gardes} déjà coché(s)",
            "date_courses": d.isoformat()}


@outil("supprimer_liste_courses", "Supprimer une liste de courses",
       "Supprime la liste de courses de cette date et tous ses articles.",
       {"date_courses": {"type": "string", "description": "AAAA-MM-JJ"}}, requis=["date_courses"], destructif=True)
def supprimer_liste_courses(utilisateur, date_courses):
    liste = _liste(date_courses)
    liste.delete()
    return {"resultat": f"Liste du {liste.libelle} supprimée"}


# --------------------------------------------------------------------------- frigo

@outil("ajouter_au_frigo", "Noter un reste au frigo", "Ajoute un reste à la liste du frigo.",
       {"nom": TEXTE, "quantite": TEXTE, "remarque": TEXTE}, requis=["nom"])
def ajouter_au_frigo(utilisateur, nom, quantite="", remarque=""):
    r = ResteFrigo.objects.create(nom=nom.strip(), quantite=quantite, remarque=remarque, ajoute_par=utilisateur)
    return {"resultat": f"« {r} » noté au frigo", "id": r.id}


@outil("retirer_du_frigo", "Retirer un reste du frigo", "Retire un reste (utilisé ou jeté) par son identifiant (lire_frigo).",
       {"id": {"type": "integer"}}, requis=["id"], destructif=True)
def retirer_du_frigo(utilisateur, id):
    r = ResteFrigo.objects.filter(pk=id).first()
    if not r:
        raise ErreurOutil(f"Reste {id} introuvable (voir lire_frigo).")
    r.delete()
    return {"resultat": f"« {r} » retiré du frigo"}


# --------------------------------------------------------------------------- plan complet

@outil("importer_plan_complet", "Remplacer tout le plan",
       "Remplace TOUT le plan (recettes, jours, listes) par le fichier fourni, au format d'exporter_plan_complet "
       "(docs/FORMAT_PLAN.md). Sert à préparer de nouvelles semaines. Les cases cochées identiques sont gardées. "
       "Réservé aux comptes « équipe ». À n'utiliser qu'après accord explicite de la personne.",
       {"plan": {"type": "object", "description": "Le plan complet (objet JSON, \"version\": 1)."}},
       requis=["plan"], destructif=True)
def importer_plan_complet(utilisateur, plan):
    if not utilisateur.is_staff:
        raise ErreurOutil("Seul un compte « équipe » peut remplacer tout le plan (comme sur la page Plan).")
    try:
        resume = importer_plan(plan, utilisateur=utilisateur)
    except PlanInvalide as e:
        raise ErreurOutil(f"Plan refusé, rien n'a été modifié : {e}")
    return {"resultat": "Plan importé : {recettes} recettes, {jours} jours, {listes} listes, {articles} articles."
            .format(**resume)}
