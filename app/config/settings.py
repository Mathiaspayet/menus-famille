"""
Réglages Django de l'appli « Menus famille ».

Tout ce qui change d'une installation à l'autre se règle par variables
d'environnement (fichier .env sur le NAS), jamais dans ce fichier.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Dossier persistant : base SQLite. Monté sur un volume Docker sur le NAS.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-not-secret"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY doit être défini (voir .env.example).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# La sonde de santé de Docker (healthcheck.py) appelle l'appli depuis l'intérieur
# du conteneur, sur 127.0.0.1 : toujours autorisé, quel que soit le .env.
# Sans cela, le conteneur est marqué « en mauvaise santé » dans Container Manager.
for _hote in ("127.0.0.1", "localhost"):
    if _hote not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_hote)
# Ex. : https://menus.mondomaine.fr — nécessaire derrière le reverse proxy HTTPS.
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "menus",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "menus.context_processors.version",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "menus.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # En production, fichiers statiques compressés et versionnés (collectstatic au build).
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accueil"
LOGOUT_REDIRECT_URL = "login"

# On reste connecté un an sur son téléphone : pas besoin de retaper le mot de passe.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365

# Derrière le reverse proxy HTTPS du NAS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
if os.environ.get("DJANGO_HTTPS", "False").lower() in ("1", "true", "yes"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Version de l'image Docker, fournie par GitHub Actions (voir Dockerfile).
BUILD_VERSION = os.environ.get("BUILD_VERSION", "dev")
BUILD_DATE = os.environ.get("BUILD_DATE", "")

# Bouton « Modifier avec Claude » : adresse d'un projet Claude dédié (facultatif).
# Vide : le bouton ouvre une nouvelle conversation avec la question pré-remplie.
# Par défaut : le projet « Menus famille » du propriétaire de l'appli (l'identifiant
# seul ne donne aucun accès : le projet reste privé). Remplaçable par la variable
# d'environnement ; CLAUDE_PROJECT_URL=aucun pour revenir à une conversation simple.
CLAUDE_PROJECT_URL_DEFAUT = "https://claude.ai/project/01a1fd94-3440-73d6-b97f-2db446cbfef4"
CLAUDE_PROJECT_URL = os.environ.get("CLAUDE_PROJECT_URL", "").strip() or CLAUDE_PROJECT_URL_DEFAUT
if CLAUDE_PROJECT_URL.lower() == "aucun":
    CLAUDE_PROJECT_URL = ""

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
