#!/bin/bash
set -e

echo "=== Menus famille - démarrage (version ${BUILD_VERSION:-dev}) ==="

# Met la base à jour si le code a ajouté des tables ou des colonnes
python manage.py migrate --noinput

# Premier démarrage : crée le compte administrateur (Mathias) depuis le .env.
# Sans effet si le compte existe déjà.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null || true
fi

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
