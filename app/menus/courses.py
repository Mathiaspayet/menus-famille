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
import re

from django.utils import timezone

from .models import Article

JOURS = {"lun": 0, "mar": 1, "mer": 2, "jeu": 3, "ven": 4, "sam": 5, "dim": 6}
MOTIF = re.compile(r"\b(lun|mar|mer|jeu|ven|sam|dim)[a-z]*\.?\s+(\d{1,2})\b", re.IGNORECASE)
HORIZONS = [(1, "Demain"), (3, "3 jours"), (7, "7 jours"), (14, "14 jours")]
HORIZON_PAR_DEFAUT = 14
NOMS_JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def date_d_usage(article):
    """Date du premier repas qui utilise l'article (sert à trier la liste)."""
    if article.pour_le:
        return article.pour_le
    depart = article.liste.date_courses
    for m in MOTIF.finditer(article.commentaire or ""):
        jour_semaine, numero = JOURS[m.group(1).lower()], int(m.group(2))
        candidates = [depart + datetime.timedelta(days=d) for d in range(-3, 46)]
        trouvees = [d for d in candidates if d.day == numero and d.weekday() == jour_semaine] \
            or [d for d in candidates if d.day == numero]
        if trouvees:
            return trouvees[0]
    return depart


CONSERVATION = re.compile(r"^(à congeler|congeler|frigo|au frigo|congélateur)$", re.IGNORECASE)


def preparer_affichage(article, aujourdhui):
    """Commentaire à afficher sous l'article, sans ce que la liste dit déjà :
    la date (titre du groupe) et « À congeler / Frigo », qui dépendaient de
    l'ancien jour de courses fixe. On conseille de congeler seulement si
    l'article est acheté au moins 2 jours avant son repas."""
    morceaux = []
    for morceau in (article.commentaire or "").split("·"):
        morceau = morceau.strip()
        dates = list(MOTIF.finditer(morceau))
        reste = MOTIF.sub("", morceau).strip(" ,").lower()
        if not morceau or CONSERVATION.match(morceau):
            continue
        if len(dates) == 1 and reste in ("", "pour") and article.prio.day == int(dates[0].group(2)):
            continue   # « dim 22 », « Pour dim 22 » : la date est déjà le titre du groupe
        morceaux.append(morceau)
    article.note = " · ".join(morceaux)
    article.a_congeler = (article.congeler or article.magasin == "boucher") and (article.prio - aujourdhui).days >= 2


def libelle_jour(date, aujourdhui):
    ecart = (date - aujourdhui).days
    nom = f"{NOMS_JOURS[date.weekday()]} {date.day} {MOIS[date.month - 1]}"
    if ecart == 0:
        return f"Aujourd'hui · {nom}"
    if ecart == 1:
        return f"Demain · {nom}"
    return nom


def tous_les_articles():
    """Tous les articles, chacun avec sa date d'usage (attribut « prio »)."""
    articles = list(Article.objects.select_related("liste", "coche_par"))
    for a in articles:
        a.prio = date_d_usage(a)
    return articles


def liste_globale(magasin, jours, aujourdhui=None):
    """Ce qu'il faut afficher sur la page Courses pour un magasin et un horizon."""
    aujourdhui = aujourdhui or timezone.localdate()
    fin = aujourdhui + datetime.timedelta(days=jours)
    articles = tous_les_articles()
    for a in articles:
        preparer_affichage(a, aujourdhui)

    a_acheter = {code: 0 for code, _ in Article.MAGASINS}
    for a in articles:
        if not a.coche and aujourdhui <= a.prio <= fin:
            a_acheter[a.magasin] += 1

    du_magasin = sorted((a for a in articles if a.magasin == magasin),
                        key=lambda a: (a.prio, a.categorie, a.ordre, a.nom))
    groupes = []
    for a in du_magasin:
        if a.coche or not aujourdhui <= a.prio <= fin:
            continue
        if not groupes or groupes[-1]["date"] != a.prio:
            groupes.append({"date": a.prio, "libelle": libelle_jour(a.prio, aujourdhui), "articles": []})
        groupes[-1]["articles"].append(a)

    return {
        "fin": fin,
        "groupes": groupes,
        "a_acheter": a_acheter,
        "plus_tard": [a for a in du_magasin if not a.coche and a.prio > fin],
        "passes": [a for a in du_magasin if not a.coche and a.prio < aujourdhui],
        "achetes": [a for a in du_magasin if a.coche and a.prio >= aujourdhui],
    }
