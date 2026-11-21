# Installer Menus famille sur le Synology

Même principe que la gestion locative : GitHub fabrique l'image, le NAS la télécharge,
et le **Watchtower déjà installé** (celui de la gestion locative) la tient à jour.
Il n'y a pas de second Watchtower à installer. Compter 20 minutes.

## 1. Vérifier que l'image existe sur GitHub

1. Sur GitHub, dépôt `menus-famille` → onglet **Actions** : le workflow « Tests & déploiement » doit être vert.
2. Sur ta page de profil GitHub → onglet **Packages** → `menus-famille` → **Package settings** :
   en bas, **Change visibility** → **Public** (sinon le NAS ne peut pas la télécharger sans identifiants).
   Il n'y a que le code dans l'image, aucune donnée.

## 2. Préparer le dossier sur le NAS

En SSH sur le NAS :

```bash
sudo mkdir -p /volume1/docker/menus-famille/data
cd /volume1/docker/menus-famille
sudo wget -O docker-compose.yml https://raw.githubusercontent.com/Mathiaspayet/menus-famille/main/docker-compose.synology.yml
sudo wget -O .env https://raw.githubusercontent.com/Mathiaspayet/menus-famille/main/.env.example
```

(Ou crée ces deux fichiers avec File Station / l'éditeur de texte de DSM.)

## 3. Remplir le `.env`

```bash
sudo vi .env
```

- `DJANGO_SECRET_KEY` : une longue chaîne aléatoire. Pour en générer une :
  `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_ALLOWED_HOSTS` : l'IP du NAS (ex. `192.168.1.20`) et, plus tard, le nom de domaine.
- `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` : ton compte (créé au premier démarrage).

## 4. Lancer avec Container Manager

1. **Container Manager** → **Projet** → **Créer**.
2. Nom : `menus-famille`, chemin : `/volume1/docker/menus-famille`, « Utiliser le docker-compose.yml existant ».
3. Suivant → Terminé. Un seul conteneur démarre : `menus_famille`.
   Les mises à jour sont assurées par le conteneur `watchtower` déjà présent
   (projet gestion-locative), grâce à l'étiquette
   `com.centurylinklabs.watchtower.scope=gestion-locative`.
4. Ouvre `http://IP-DU-NAS:8010` et connecte-toi.

## 5. Importer le plan et créer le deuxième compte

1. En haut à droite, **Plan** → **Importer** → choisis `plan-menus-famille.json`.
2. Lien **Administration** → **Utilisateurs** → **Ajouter** : un identifiant et un mot de passe pour ta compagne.
   Puis renseigne son prénom (affiché dans l'appli). Ne coche pas « statut équipe » : elle verra tout,
   cochera les courses et le frigo, mais ne pourra pas remplacer le plan.

## 6. Accès depuis les téléphones (hors de la maison)

Deux possibilités, comme pour la gestion locative :

- **Tailscale** (le plus simple et le plus sûr) : installe l'appli Tailscale sur le téléphone de ta compagne,
  puis ouvre `http://NOM-DU-NAS:8010` (ajoute ce nom à `DJANGO_ALLOWED_HOSTS`).
- **Reverse proxy HTTPS** : Panneau de configuration → Portail de connexion → Avancé → Proxy inversé.
  Source `https://menus.ton-domaine.fr` (port 443), destination `http://localhost:8010`.
  Dans le `.env` : ajoute le domaine à `DJANGO_ALLOWED_HOSTS`, mets
  `DJANGO_CSRF_TRUSTED_ORIGINS=https://menus.ton-domaine.fr` et `DJANGO_HTTPS=True`.
  Ce mode sera nécessaire pour l'étape MCP (Claude doit pouvoir joindre l'appli).

Sur le téléphone : ouvrir l'adresse **en HTTPS**, puis **Partager → Sur l'écran d'accueil** (iPhone, dans
Safari) ou **Installer** dans le bandeau proposé par l'appli (Android, dans Chrome ; sinon **⋮ → Installer
l'appli**). L'appli s'ouvre alors comme une vraie appli.

**Sans réseau** (au fond du supermarché…) : les pages déjà ouvertes sur le téléphone restent consultables,
ainsi que les autres magasins de la liste et les autres jours de la semaine. Les cases cochées restent cochées
et sont envoyées au NAS dès le retour du réseau (message orange en bas de l'écran tant qu'il en reste).
Le mode hors connexion ne fonctionne qu'en HTTPS (pas avec l'adresse `http://IP:8010`).

## 7. Connecter Claude (facultatif)

Une fois l'accès HTTPS en place (étape 6), Claude peut lire et modifier directement les menus,
les courses et le frigo. Mode d'emploi : [docs/MCP.md](docs/MCP.md). Il n'y a rien à régler
sur le NAS : il suffit d'ajouter le connecteur `https://ton-domaine/mcp` dans Claude.

Pour vérifier qu'une mise à jour est arrivée : le **bas de chaque page** affiche la date de la
version en service.

## 8. Sauvegarde

Ajoute `/volume1/docker/menus-famille/data` à ta tâche **Hyper Backup** : c'est là que tout est stocké.

## Dépannage

- **Page « Bad Request (400) »** : l'adresse utilisée n'est pas dans `DJANGO_ALLOWED_HOSTS`.
- **« CSRF verification failed » en HTTPS** : vérifier `DJANGO_CSRF_TRUSTED_ORIGINS`.
- **Les logs** : Container Manager → Conteneur → `menus_famille` → Journal.
- **L'appli ne se met pas à jour** : regarder le journal du conteneur `watchtower`
  (celui de la gestion locative) et vérifier que l'image GitHub est bien publique.
- **Après une modification du `.env`** : Projet → `menus-famille` → Arrêter puis Démarrer.
