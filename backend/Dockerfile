FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Prevent pip from running as root warning noise
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only the minimal OS packages needed.
# curl: used by HEALTHCHECK. postgresql-client: used by pg_dump backup task.
# No build tools — use the pre-built psycopg[binary] wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install Python dependencies before copying app code so Docker can cache this layer.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source.
COPY . /app

# Collect static files at build time with a throwaway secret key.
# DJANGO_DEBUG=0 ensures production storage backend (WhiteNoise) is used.
RUN DJANGO_SECRET_KEY=build-placeholder \
    DJANGO_DEBUG=0 \
    DJANGO_ENV=production \
    python manage.py collectstatic --noinput --clear

RUN chmod +x /app/start.sh

# LOW: Run as a non-root user to limit blast radius of any RCE.
RUN useradd --uid 1001 --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# LOW-005: Container health probe — fails fast if the app cannot serve requests.
# start-period gives migrations time to complete before health checks begin.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

CMD ["/app/start.sh"]
