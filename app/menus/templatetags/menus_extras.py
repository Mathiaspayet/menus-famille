"""Filtres de gabarits de l'appli."""
import re

from django import template

from menus.courses import _lire_quantite

register = template.Library()

CRU = re.compile(r"\b(crue?s?)\b", re.IGNORECASE)
BOITE = re.compile(r"^bo[iî]tes? de demain", re.IGNORECASE)


@register.filter
def total_assiette(lignes):
    """Poids total de l'assiette de chacun (en g), quand le tableau des portions a
    au moins deux lignes en grammes : « Porc et légumes 330 g » + « Nouilles 130 g »
    → 460 g. Utile pour un plat mélangé : on pèse l'assiette entière.
    Les lignes « crues » (poids avant cuisson) et « Boîte de demain » ne comptent pas."""
    lignes_g = []
    for ligne in lignes or []:
        if not ligne or BOITE.match(str(ligne[0]).strip()) or CRU.search(str(ligne[0])):
            continue
        valeurs = []
        for case in ligne[1:]:
            case = (case or "").strip()
            if case in ("", "–", "-"):
                valeurs.append(0)
                continue
            lu = _lire_quantite(case)
            if not lu or lu[1] != "g":
                valeurs = None
                break
            valeurs.append(lu[0])
        if valeurs and any(valeurs):
            lignes_g.append(valeurs)
    if len(lignes_g) < 2:
        return None
    n = max(len(v) for v in lignes_g)
    totaux = [sum(v[i] for v in lignes_g if i < len(v)) for i in range(n)]
    return [f"{round(t)} g" if t else "–" for t in totaux]
