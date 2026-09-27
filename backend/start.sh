#!/bin/sh
set -e

echo "Running database migrations..."
flask --app backend.run:app db upgrade

echo "Seeding database..."
python backend/seed.py

echo "Starting Gunicorn..."
exec gunicorn --config backend/gunicorn.conf.py backend.run:app
