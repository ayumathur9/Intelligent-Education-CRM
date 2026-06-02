#!/bin/bash
# Production entrypoint for the CRM backend.
# Runs as non-root (appuser). Fails loudly on any error.
set -euo pipefail

echo "=== Validating Django configuration ==="
python manage.py check --deploy --fail-level WARNING

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
    print("ERROR: DJANGO_SUPERUSER_PASSWORD must be at least 12 characters.", file=sys.stderr)
    sys.exit(1)

if User.objects.filter(email=email).exists():
    print(f"Superuser already exists: {email}")
else:
    User.objects.create_superuser(email=email, password=password, full_name=name)
    print(f"Superuser created: {email}")
PYEOF

echo "=== Ensuring media directories exist ==="
mkdir -p media/tutorials

echo "=== Starting Daphne ASGI server on :8000 ==="
# --proxy-headers: trust X-Forwarded-Proto from Railway's load balancer
# --access-log  : structured access logging to stdout
# -v 1          : production verbosity (warnings/errors only)
exec daphne \
    -v 1 \
    --proxy-headers \
    --access-log - \
    -b 0.0.0.0 \
    -p 8000 \
    config.asgi:application
