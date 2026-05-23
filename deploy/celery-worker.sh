#!/bin/bash
# =============================================================================
# Celery worker startup script for Intelligent Education CRM.
# Run via Railway/Docker CMD or systemd unit.
# =============================================================================
set -euo pipefail

# Reliability: acks_late + reject_on_worker_lost already set in settings.
# concurrency=2 is safe for <50 users; raise via CELERY_WORKER_CONCURRENCY env.
exec celery -A config.celery_app worker \
    --loglevel=info \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-2}" \
    --prefetch-multiplier=1 \
    --without-gossip \
    --without-mingle \
    --without-heartbeat \
    -Q default
