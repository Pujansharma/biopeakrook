#!/bin/bash

gunicorn  core.wsgi:application  -c ./assets/scripts/gunicorn.conf.py