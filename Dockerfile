# ============================================================
# Dockerfile - Menus famille (production)
# ============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

ARG BUILD_VERSION=dev
ENV BUILD_VERSION=${BUILD_VERSION}

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY docker-entrypoint.sh healthcheck.py /app/
RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /app/data

# Fichiers statiques (CSS, JS, icônes) préparés une fois pour toutes au build
RUN DJANGO_SECRET_KEY=build-placeholder DJANGO_DEBUG=False python manage.py collectstatic --noinput

EXPOSE 8000

# Sans healthcheck, un conteneur qui démarre mais ne répond plus reste « up ».
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
