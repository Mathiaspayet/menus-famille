# Format du fichier de plan (JSON)

Ce format sert à l'**export** (bouton « Télécharger le plan ») et à l'**import**
(page Plan). Pour faire modifier les menus par Claude : exportez, envoyez le
fichier avec votre demande, et demandez-lui de **renvoyer le fichier complet au
même format**. Vous pouvez lui coller cette page pour qu'il connaisse les règles.

## Structure générale

```json
{
  "version": 1,
  "personnes": ["Parent 1", "Parent 2", "Enfant 1", "Enfant 2"],
  "debut": "2026-11-16",
  "recettes": { "<cle>": { ...recette... } },
  "petits_dejeuners": { "A": { ...formule... } },
  "semaines": [ { "n": 1, "label": "16 – 22 nov.", "days": [ ...jours... ] } ],
  "listes": [ { ...liste de courses... } ],
  "frigo": [ { "nom": "Courgettes", "quantite": "300 g", "remarque": "" } ],
  "infos_html": "<div class=\"card\">…</div>"
}
```

## Recette

```json
"curry_poulet": {
  "t": "Curry de poulet, potimarron et épinards",
  "time": "25 min",
  "boxes": true,              // cuisiner 2 parts de plus pour les boîtes du lendemain
  "fire": "Sriracha",         // pot du feu (piment à table), ou null
  "des": "1 clémentine chacun",
  "note": null,
  "ing": ["625 g de filets de poulet", "..."],
  "steps": ["Lancez le riz...", "..."],
  "por": [["Curry", "330 g", "410 g", "140 g", "100 g"]]   // une colonne par personne
}
```

Portions et « Qui mange ? » : sur la page du jour, on peut retirer une personne
(ou les boîtes du lendemain) ; la colonne « Total » additionne alors les parts des
présents. Pour en profiter, écrire viandes et féculents en deux lignes
(`"Porc cru"`, `"Porc cuit (≈)"`) et les parts des boîtes sur des lignes
`"Boîte de demain : porc cru"` : l'appli affiche aussi « À peser (cru) », la somme
des lignes crues de la même denrée. Valeurs additionnables : `"120 g"`, `"400 ml"`,
`"1 pavé"`, `"⅗ de pavé"`, `"1½"` ; une case vide compte pour zéro.

## Jour

```json
{
  "iso": "2026-11-24", "full": "Mardi 24 nov.",
  "todo": ["Sortez du congélateur : ..."],
  "pdj": "B",                                   // code d'une formule, ou null
  "midi": {"lbl": "Boîte : ...", "sub": "Enfants à la cantine", "r": "porc_gingembre", "box": true},
  "gouter": "1 compote, 2 petits-beurre",
  "soir": "dahl_lentilles",                     // clé d'une recette
  "prep": "box_lentilles",                      // facultatif : à préparer pour le lendemain
  "remarque": "curry reporté à jeudi"           // facultatif
}
```

`midi` : texte seul (`lbl`, `sub`), ou recette (`r`). Avec `"box": true`, la carte
affiche `lbl`/`sub` et la recette en détail (cas des boîtes repas).

## Liste de courses

```json
{
  "label": "Mar. 24 nov.", "shop": "2026-11-24",
  "range": "du mar. 24 nov. soir au lun. 30 nov. goûter",
  "shops": {
    "boucher": [{"c": "Volaille", "items": [["Filets de poulet", "625 g", "À congeler", 1, 0, 0]]}],
    "primeur": [...],
    "leclerc": [...]
  }
}
```

Un article = `[nom, quantité, commentaire, à congeler (0/1), à vérifier (0/1), coché (0/1)]`.
Le 6e élément (coché) est facultatif : s'il est absent, l'appli garde l'état déjà
coché pour un article de même nom, même magasin et même date de courses.

## Règles à l'import

- Toute recette citée dans un jour doit exister dans `recettes`, sinon le fichier est refusé
  (et l'ancien plan reste intact).
- Le plan (recettes, jours, listes) est **remplacé en entier**.
- La clé `frigo`, si elle est présente, remplace la liste des restes ; absente, le frigo n'est pas touché.
