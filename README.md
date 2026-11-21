# Menus famille

Petite appli web auto-hébergée (Synology + Docker) pour une famille de 4 :

- **Semaine** : menus du jour (petit-déj, midi, goûter, soir), recettes détaillées, « À faire » du jour, remarque libre.
- **Courses** : listes par magasin (boucher, primeur, Leclerc). **Les cases cochées sont enregistrées sur le NAS et partagées** :
  si l'un fait le primeur lundi, l'autre voit ce qui reste à acheter mardi.
- **Frigo** : on note ce qui reste, pour que Claude en tienne compte.
- **Modifier avec Claude** : un bouton ouvre Claude avec la question pré-remplie.
- **Plan** : export / import du plan en JSON, pour le faire réajuster par Claude ([format](docs/FORMAT_PLAN.md)).

Le dépôt ne contient **aucune donnée familiale** : le plan est importé depuis l'appli et vit uniquement dans la base du NAS.

## Comment c'est construit

| Élément | Rôle |
|---|---|
| `app/` | Le projet Django (Python). `menus/models.py` décrit les données, `menus/views.py` les écrans. |
| SQLite | La base, un simple fichier dans `/volume1/docker/menus-famille/data`. |
| `Dockerfile` | La recette pour fabriquer l'image (l'appli prête à tourner). |
| `.github/workflows/deploy.yml` | À chaque `push`, GitHub lance les tests puis fabrique l'image sur ghcr.io. |
| Watchtower | Sur le NAS, vérifie toutes les 5 min s'il y a une nouvelle image et redémarre l'appli avec. |

## Installer sur le NAS

Voir [GUIDE_INSTALLATION_NAS.md](GUIDE_INSTALLATION_NAS.md).

## Développer sur un PC

```bash
pip install -r requirements.txt
cd app
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py createsuperuser
python manage.py import_plan ../plan-menus-famille.json
python manage.py runserver        # http://127.0.0.1:8000
python manage.py test menus       # les tests
```

## Étape suivante prévue

Un serveur **MCP** pour que Claude (dans l'app Claude) lise et modifie directement la base du NAS,
sans passer par l'export / import.
