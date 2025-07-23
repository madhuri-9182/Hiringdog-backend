#!/bin/bash
set -e

cd /app

# Run migrations
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000

exec "$@"