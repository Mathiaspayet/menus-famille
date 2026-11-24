"""
Liste de courses unique, triée par urgence.

On ne raisonne plus par « jour de courses » : chaque article porte la date du
premier repas qui l'utilise (Article.pour_le). La page Courses rassemble tous
les articles à venir, par magasin, du plus urgent au moins urgent : on achète
les premiers selon le temps, le budget et la place au congélateur.

Pour les articles plus anciens, sans date, on la retrouve dans le commentaire
(« À congeler · sam 21 », « Pour mer 18, lun 23 ») ; à défaut, on prend la
date de la liste d'origine.
"""
import datetime
import json
import re

from django.urls import reverse
from django.utils import timezone

from .models import Article

JOURS = {"lun": 0, "mar": 1, "mer": 2, "jeu": 3, "ven": 4, "sam": 5, "dim": 6}
MOTIF = re.compile(r"\b(lun|mar|mer|jeu|ven|sam|dim)[a-z]*\.?\s+(\d{1,2})\b", re.IGNORECASE)
HORIZONS = [(1, "Demain"), (3, "3 jours"), (7, "7 jours"), (14, "14 jours")]
HORIZON_PAR_DEFAUT = 14
NOMS_JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _date_du_motif(m, depart):
    """« sam 21 » → la date proche de la liste d'origine qui tombe un samedi 21."""
    jour_semaine, numero = JOURS[m.group(1).lower()], int(m.group(2))
    candidates = [depart + datetime.timedelta(days=d) for d in range(-3, 46)]
    trouvees = [d for d in candidates if d.day == numero and d.weekday() == jour_semaine] \
        or [d for d in candidates if d.day == numero]
    return trouvees[0] if trouvees else None


def dates_d_usage(article):
    """Toutes les dates de repas connues pour l'article, triées : sa date
    d'usage (pour_le) et celles citées dans le commentaire (« Pour mer 25, sam 28 »)."""
    dates = {article.pour_le} if article.pour_le else set()
    for m in MOTIF.finditer(article.commentaire or ""):
        d = _date_du_motif(m, article.liste.date_courses)
        if d:
            dates.add(d)
    return sorted(dates) or [article.liste.date_courses]


def date_d_usage(article):
    """Date du premier repas qui utilise l'article (sert à trier la liste)."""
    return article.pour_le or dates_d_usage(article)[0]


CONSERVATION = re.compile(r"^(à congeler|congeler|frigo|au frigo|congélateur)$", re.IGNORECASE)


def note_libre(article):
    """Ce que le commentaire dit d'autre que les dates et « À congeler / Frigo »
    (affichés autrement : dates sous l'ingrédient, conseil de congélation calculé)."""
    morceaux = []
    for morceau in (article.commentaire or "").split("·"):
        morceau = morceau.strip()
        reste = MOTIF.sub("", morceau).strip(" ,").lower()
        if morceau and not CONSERVATION.match(morceau) and reste not in ("", "pour", "pour le", "et"):
            morceaux.append(morceau)
    return " · ".join(morceaux)


def tous_les_articles():
    """Tous les articles, chacun avec ses dates d'usage (« dates ») et la première (« prio »)."""
    articles = list(Article.objects.select_related("liste", "coche_par"))
    for a in articles:
        a.dates = dates_d_usage(a)
        a.prio = date_d_usage(a)
    return articles


# ----------------------------------------------------------------- regroupement

def nom_normalise(nom):
    """« Citrons jaunes », « Citron jaune » et « Chou chinois (≈ 600 g) » / « Chou chinois »
    désignent le même ingrédient."""
    n = re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", nom).lower()).strip()
    return " ".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in n.split())


def cle(article):
    return f"{article.magasin}|{nom_normalise(article.nom)}"


FRACTIONS = {"½": .5, "¼": .25, "¾": .75, "⅓": 1 / 3, "⅔": 2 / 3}


def _lire_quantite(texte):
    """« 2,5 kg » → (2500, "g") ; « 4 » → (4, "") ; « 1 tête (6 gousses) » → (1, "tête")."""
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)?\s*([½¼¾⅓⅔])?\s*(.*)$", texte or "")
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    n = (float(m.group(1).replace(",", ".")) if m.group(1) else 0) + FRACTIONS.get(m.group(2), 0)
    unite = re.sub(r"\(.*?\)", "", m.group(3)).strip().lower()
    facteurs = {"kg": (1000, "g"), "g": (1, "g"), "l": (1000, "ml"), "cl": (10, "ml"), "ml": (1, "ml")}
    if unite in facteurs:
        f, u = facteurs[unite]
        return n * f, u
    mots = unite.split()
    if mots and len(mots[0]) > 3 and mots[0][-1] in "sx":
        mots[0] = mots[0][:-1]
    return n, " ".join(mots)


def _ecrire_nombre(n):
    entier, reste = int(n), round(n - int(n), 2)
    if reste == 0:
        return str(entier)
    if reste in (.5, .25, .75):
        return (str(entier) if entier else "") + {.5: "½", .25: "¼", .75: "¾"}[reste]
    return f"{n:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def additionner(quantites):
    """Somme lisible de quantités de même nature ; sinon « 2 + 1 bouquet »."""
    quantites = [q for q in quantites if q]
    if len(quantites) <= 1:
        return quantites[0] if quantites else ""
    lues = [_lire_quantite(q) for q in quantites]
    if not all(lues) or len({u for _, u in lues}) != 1:
        return " + ".join(quantites)
    total, unite = sum(n for n, _ in lues), lues[0][1]
    if unite == "g":
        return (_ecrire_nombre(round(total / 1000, 2)) + " kg") if total >= 1000 else f"{round(total)} g"
    if unite == "ml":
        return (_ecrire_nombre(round(total / 1000, 2)) + " l") if total >= 1000 else f"{round(total)} ml"
    if not unite:
        return _ecrire_nombre(total)
    mots = unite.split()
    if total > 1 and len(mots[0]) > 2 and mots[0][-1] not in "sxz" and mots[0] not in ("cm", "mm"):
        mots[0] += "s"
    return f"{_ecrire_nombre(total)} {' '.join(mots)}"


def court(date, aujourdhui):
    """« demain », « jeu 26 », « mar 1 déc. »"""
    ecart = (date - aujourdhui).days
    if ecart == 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    texte = f"{NOMS_JOURS[date.weekday()][:3].lower()} {date.day}"
    return texte + (f" {MOIS[date.month - 1]}" if date.month != aujourdhui.month else "")


def regrouper(articles, aujourdhui, fin=None):
    """Une ligne par ingrédient : quantités additionnées, dates d'usage réunies.
    Avec « fin » : on n'énumère que les dates de la période ; un article qui sert
    aussi après (anciennes listes par lot) le signale, sa quantité les comprenant."""
    groupes = {}
    for a in articles:
        groupes.setdefault(cle(a), []).append(a)
    lignes = []
    for k, arts in groupes.items():
        arts.sort(key=lambda a: (a.prio, a.id))
        dates = sorted({d for a in arts for d in a.dates})
        noms = {a.nom for a in arts}
        notes = []
        for a in arts:
            n = note_libre(a)
            if n and n not in notes:
                notes.append(n)
        premier = arts[0].prio
        dans_periode = [d for d in dates if fin is None or d <= fin] or dates
        apres = len(dates) - len(dans_periode)
        quand = ", ".join(court(d, aujourdhui) for d in dans_periode)
        lignes.append({
            "cle": k, "articles": arts, "premier": premier, "dates": dates,
            "nom": arts[0].nom if len(noms) == 1 else re.sub(r"\s*\(.*?\)", "", arts[0].nom).strip(),
            "quantite": additionner([a.quantite for a in arts]),
            "quand": (f"{len(dans_periode)} fois : {quand}" if len(dans_periode) > 1 else f"Pour {quand}"),
            "apres": (f"+ {apres} fois après le {court(fin, aujourdhui)}, déjà compris dans la quantité" if apres else ""),
            "note": " · ".join(notes),
            "verifier": any(a.verifier for a in arts),
            "coche": all(a.coche for a in arts),
            "a_congeler": any(a.congeler or a.magasin == "boucher" for a in arts) and (premier - aujourdhui).days >= 2,
            "donnees": json.dumps([[a.id, reverse("article_cocher", args=[a.id])] for a in arts]),
        })
    lignes.sort(key=lambda l: (l["premier"], l["nom"].lower()))
    return lignes


def liste_globale(magasin, jours, aujourdhui=None):
    """Ce qu'il faut afficher sur la page Courses pour un magasin et une période :
    une ligne par ingrédient, du plus urgent au moins urgent."""
    aujourdhui = aujourdhui or timezone.localdate()
    fin = aujourdhui + datetime.timedelta(days=jours)
    articles = tous_les_articles()
    dans_la_periode = lambda a: aujourdhui <= a.prio <= fin  # noqa: E731

    a_acheter = {code: len({cle(a) for a in articles if a.magasin == code and not a.coche and dans_la_periode(a)})
                 for code, _ in Article.MAGASINS}
    du_magasin = [a for a in articles if a.magasin == magasin]
    return {
        "fin": fin,
        "lignes": regrouper([a for a in du_magasin if not a.coche and dans_la_periode(a)], aujourdhui, fin),
        "a_acheter": a_acheter,
        "plus_tard": regrouper([a for a in du_magasin if not a.coche and a.prio > fin], aujourdhui),
        "passes": regrouper([a for a in du_magasin if not a.coche and a.prio < aujourdhui], aujourdhui),
        "achetes": regrouper([a for a in du_magasin if a.coche and a.prio >= aujourdhui], aujourdhui),
    }
