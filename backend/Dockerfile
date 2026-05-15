FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN DJANGO_SECRET_KEY=build-placeholder DJANGO_DEBUG=0 python manage.py collectstatic --noinput

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
