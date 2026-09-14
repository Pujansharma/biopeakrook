#!/bin/bash
set -euo pipefail

python manage.py collectstatic --noinput --clear
python manage.py migrate
gunicorn  core.wsgi:application  -c ./assets/scripts/gunicorn.conf.py