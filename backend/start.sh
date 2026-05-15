#!/bin/bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Starting Daphne on port 8000 ==="
exec daphne -v 2 config.asgi:application --bind 0.0.0.0 --port 8000
