#!/bin/bash
set -uo pipefail

reminder_exit=0
outbox_exit=0
scan_exit=0
renewal_exit=0
health_enqueue_exit=0
health_worker_exit=0
python manage.py enqueue_appointment_reminders || reminder_exit=$?
python manage.py process_communication_outbox || outbox_exit=$?
python manage.py process_appointment_exception_scans || scan_exit=$?
python manage.py process_google_calendar_channel_expiry_renewal || renewal_exit=$?
python manage.py enqueue_health_freshness_checks || health_enqueue_exit=$?
python manage.py process_health_jobs || health_worker_exit=$?

exit_code=$reminder_exit
if [ "$outbox_exit" -gt "$exit_code" ]; then
  exit_code=$outbox_exit
fi
if [ "$scan_exit" -gt "$exit_code" ]; then
  exit_code=$scan_exit
fi
if [ "$renewal_exit" -gt "$exit_code" ]; then
  exit_code=$renewal_exit
fi
if [ "$health_enqueue_exit" -gt "$exit_code" ]; then
  exit_code=$health_enqueue_exit
fi
if [ "$health_worker_exit" -gt "$exit_code" ]; then
  exit_code=$health_worker_exit
fi
exit "$exit_code"
