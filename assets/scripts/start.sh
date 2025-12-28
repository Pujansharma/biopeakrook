#!/bin/bash

python manage.py collectstatic --noinput --clear
python manage.py migrate

exec ./assets/scripts/entrypoint.sh
