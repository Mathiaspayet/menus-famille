"""Variables disponibles dans tous les gabarits."""
import datetime

from django.conf import settings
from django.utils import timezone

# Heure à laquelle l'appli a démarré : après une mise à jour par Watchtower,
# le conteneur est recréé, donc cette heure change aussi.
DEMARREE_LE = timezone.now()


def infos_version():
    """Code court du commit et date de fabrication de l'image (None hors Docker)."""
    try:
        date = datetime.datetime.fromisoformat(settings.BUILD_DATE) if settings.BUILD_DATE else None
    except ValueError:
        date = None
    if date and timezone.is_naive(date):
        date = timezone.make_aware(date, datetime.timezone.utc)
    return {"code": settings.BUILD_VERSION[:7] or "dev", "date": date, "demarree_le": DEMARREE_LE}


def version(request):
    return {"version_appli": infos_version()}
