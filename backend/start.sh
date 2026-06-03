#!/bin/bash
# Production entrypoint for the CRM backend.
# Runs as non-root (appuser). Fails loudly on any error.
set -euo pipefail

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Creating superuser (if env vars are set) ==="
python - <<'PYEOF'
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.users.models import User

email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()
name = os.environ.get("DJANGO_SUPERUSER_NAME", "Admin").strip()

if not email or not password:
    print("DJANGO_SUPERUSER_EMAIL / _PASSWORD not set — skipping superuser creation.")
    sys.exit(0)

if len(password) < 12:
    print("WARNING: DJANGO_SUPERUSER_PASSWORD is shorter than 12 characters — skipping superuser creation.", file=sys.stderr)
    sys.exit(0)

if User.objects.filter(email=email).exists():
    print(f"Superuser already exists: {email}")
else:
    User.objects.create_superuser(email=email, password=password, full_name=name)
    print(f"Superuser created: {email}")
PYEOF

echo "=== Ensuring media directories exist ==="
mkdir -p media/tutorials

echo "=== Starting server on port 8000 ==="
exec gunicorn config.asgi:application \
    -k uvicorn.workers.UvicornWorker \
    --workers 2 \
    --bind 0.0.0.0:8000 \
    --proxy-headers \
    --forwarded-allow-ips="*" \
    --timeout 120 \
    --access-logfile -
