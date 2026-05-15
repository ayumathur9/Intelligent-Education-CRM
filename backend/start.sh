#!/bin/bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating superuser if set ==="
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput \
        --email "$DJANGO_SUPERUSER_EMAIL" \
        --full_name "${DJANGO_SUPERUSER_NAME:-Admin}" \
        || echo "Superuser already exists, skipping."
fi

echo "=== Starting Daphne on port 8000 ==="
exec daphne -v 2 config.asgi:application --bind 0.0.0.0 --port 8000
