#!/bin/sh
set -eu

# Migrations run before the app serves anything.
python -c "import app"

exec gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 --access-logfile - app:app
