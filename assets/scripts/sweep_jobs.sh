#!/bin/bash
set -uo pipefail

outbox_exit=0
scan_exit=0
python manage.py process_communication_outbox || outbox_exit=$?
python manage.py process_appointment_exception_scans || scan_exit=$?
if [ "$outbox_exit" -gt "$scan_exit" ]; then
    exit "$outbox_exit"
fi
exit "$scan_exit"
