#!/bin/bash
# =============================================================================
# Celery Beat scheduler startup script for Intelligent Education CRM.
# Only ONE beat process must run in the cluster (it's not horizontally scalable).
# =============================================================================
set -euo pipefail

exec celery -A config.celery_app beat \
    --loglevel=info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
