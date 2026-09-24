# ---------------------------------------------------------------------------
# Warrigal Park FC — container image
#
# The application has no third-party dependencies, so the image is just the
# Python runtime plus the source tree.  Build from the repository root:
#
#   docker build -f deploy/Dockerfile -t warrigal-park-fc .
#   docker run --rm -p 8080:8080 -e APP_SEED=false -v warrigal-data:/data warrigal-park-fc
# ---------------------------------------------------------------------------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Warrigal Park FC Member Registration & Team Roster System" \
      org.opencontainers.image.description="Community football club registration system (ISYS3001 Assessment 2)" \
      org.opencontainers.image.source="https://github.com/colacolaco/warrigal-park-fc"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    APP_DB_PATH=/data/warrigal_park.db \
    APP_SEED=false \
    APP_DEBUG=false

WORKDIR /app

# Only the source is copied; the development database and .env never enter the
# image because .dockerignore excludes them.
COPY . /app

# Run as an unprivileged account, and give it the data volume only.
RUN useradd --create-home --shell /usr/sbin/nologin warrigal \
    && mkdir -p /data \
    && chown -R warrigal:warrigal /data /app
USER warrigal

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4).status == 200 else 1)"

CMD ["python", "wsgi.py"]
