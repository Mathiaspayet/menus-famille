# Instructions projet — pour Claude Code

Ce fichier est lu automatiquement par Claude Code. **L'utilisateur est
débutant : explique chaque étape simplement, en français, et demande
confirmation avant toute action irréversible (envoi de code, suppression de
données, migration de base).**

---

## 1. Le projet

`menus-famille` : petite appli web pour une famille de 4 (2 adultes en
perte de poids progressive, 2 enfants qui mangent normalement). Elle affiche les
menus de la semaine et les recettes, gère des **listes de courses partagées**
(cases cochées enregistrées sur le serveur, visibles par les deux parents) et un
**inventaire du frigo**.

Elle tourne dans Docker sur un NAS Synology DS218+ (x86_64).

```
  Claude Code            GitHub                          NAS Synology
  ┌──────────┐  push   ┌───────────────────┐  pull     ┌────────────────────┐
  │ ce dépôt │ ──────► │ Actions : tests   │ ────────► │ menus_famille :8010│
  └──────────┘         │ puis image ghcr.io│           │ + watchtower_menus │
                       └───────────────────┘           └────────────────────┘
```

Chaque push sur `main` : tests, puis image `ghcr.io/mathiaspayet/menus-famille:latest`.
Watchtower (scope `menus-famille`) la déploie tout seul en ~5 min.

## 2. Règles importantes

- **Dépôt public : aucune donnée familiale dans le code ni dans les tests.**
  Le plan (menus, prénoms, allergies…) est importé depuis l'appli et ne vit que
  dans la base SQLite du NAS. `plan*.json` est dans `.gitignore`. Dans les tests,
  utiliser « Parent 1 », « Enfant 1 », etc.
- Toujours lancer les tests avant de pousser :
  `cd app && DJANGO_DEBUG=1 DATA_DIR=/tmp/menus-data python manage.py test menus`
- Toute modification de `models.py` demande une migration
  (`python manage.py makemigrations menus`) : elle s'applique au démarrage du conteneur.
- Garder le format du plan rétrocompatible (voir `docs/FORMAT_PLAN.md`) : des
  fichiers exportés existent chez l'utilisateur.

## 3. Ports déjà utilisés sur le NAS (projets de l'utilisateur)

| Port NAS | Projet |
|---|---|
| 8000 | logiciel-gestion-locative |
| **8010** | **menus-famille (ce projet)** |
| 8020 | immo (veille immobilière) |
| 8080, 8081 | comptage-vehicules |
| 8095 | audio-recorder |
| 8100 | suivi-prix-essence |
| 3000 (local) | mikromcp (dépôt Mon-ha) |

Avant de choisir un nouveau port, vérifier ce tableau (et le tenir à jour).

## 4. Structure

```
app/config/        réglages Django (tout se règle par variables d'environnement)
app/menus/
  models.py        Plan, Recette, PetitDej, Jour, ListeCourses, Article, ResteFrigo
  plan_io.py       import / export JSON du plan (cœur de la logique)
  views.py         écrans ; courses.js = cases cochées + relecture toutes les 8 s
  tests.py
docs/FORMAT_PLAN.md   format du fichier de plan
GUIDE_INSTALLATION_NAS.md
```

## 5. Feuille de route

1. ✅ Appli sur le NAS : menus, courses partagées, frigo, export/import.
2. **Serveur MCP** dans l'appli (ex. endpoint `/mcp`, protégé par jeton) pour
   que Claude, depuis l'app Claude de l'utilisateur, lise et modifie directement
   la base : lire le plan d'un jour, remplacer un repas, cocher/décocher,
   gérer le frigo, régénérer une liste de courses. Nécessite l'accès HTTPS
   via le reverse proxy du NAS. Pas de clé API Anthropic (l'utilisateur ne
   veut pas de coût en plus de son abonnement).
3. Projet Claude « Menus famille » avec les consignes ; le bouton
   « Modifier avec Claude » pointera dessus (`CLAUDE_PROJECT_URL`).
