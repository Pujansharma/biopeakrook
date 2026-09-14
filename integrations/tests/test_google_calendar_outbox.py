from unittest.mock import patch

from django.test import TestCase, override_settings

from appointments.utils.constants import AppointmentStatus
from integrations.google_calendar.google_sync import (
    google_calendar_event_id,
    sync_appointment_with_google,
)
from integrations.tests.test_whatsapp_outbox import create_appointment


class GoogleDesiredStateTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()

    def test_deterministic_event_id_is_appointment_hex(self):
        self.assertEqual(
            google_calendar_event_id(self.appointment),
            self.appointment.pk.hex,
        )

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch("integrations.google_calendar.google_sync.get_valid_access_token")
    @patch("integrations.google_calendar.google_sync.get_fixed_calendar_organizer")
    @patch("integrations.google_calendar.google_sync.calendar_api.insert_event")
    def test_confirmed_appointment_inserts_with_deterministic_id(
        self, mock_insert, mock_organizer, mock_token
    ):
        organizer = mock_organizer.return_value
        organizer.pk = self.appointment.pk
        mock_token.return_value = "access-token"
        mock_insert.return_value = {
            "id": self.appointment.pk.hex,
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
        }
        skip_reason = sync_appointment_with_google(self.appointment.pk)
        self.assertIsNone(skip_reason)
        mock_insert.assert_called_once()
        self.assertEqual(
            mock_insert.call_args.kwargs["event_id"],
            self.appointment.pk.hex,
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.google_event_id, self.appointment.pk.hex)
        self.assertEqual(
            self.appointment.google_meet_link,
            "https://meet.google.com/abc-defg-hij",
        )

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch("integrations.google_calendar.google_sync.get_valid_access_token")
    @patch("integrations.google_calendar.google_sync.get_fixed_calendar_organizer")
    @patch("integrations.google_calendar.google_sync.calendar_api.delete_event")
    def test_cancelled_appointment_deletes_event(
        self, mock_delete, mock_organizer, mock_token
    ):
        self.appointment.status = AppointmentStatus.CANCELLED
        self.appointment.google_event_id = self.appointment.pk.hex
        self.appointment.save(
            update_fields=["status", "google_event_id", "updated_at"]
        )
        mock_organizer.return_value.pk = self.appointment.pk
        mock_token.return_value = "access-token"
        skip_reason = sync_appointment_with_google(self.appointment.pk)
        self.assertIsNone(skip_reason)
        mock_delete.assert_called_once()
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.google_event_id, self.appointment.pk.hex)
