#!/bin/bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating superuser if set ==="
python - <<'PYEOF'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.users.models import User
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
name = os.environ.get("DJANGO_SUPERUSER_NAME", "Admin")
if email and password:
    if not User.objects.filter(email=email).exists():
        User.objects.create_superuser(email=email, password=password, full_name=name)
        print(f"Superuser created: {email}")
    else:
        print(f"Superuser already exists: {email}")
else:
    print("No superuser env vars set, skipping.")
PYEOF

echo "=== Starting Daphne on port 8000 ==="
exec daphne -v 2 config.asgi:application --bind 0.0.0.0 --port 8000
