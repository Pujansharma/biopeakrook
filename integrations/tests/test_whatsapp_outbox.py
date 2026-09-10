from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.centers.models import Center
from accounts.customers.models import Customer, CustomerProfile
from accounts.users.models import User
from appointments.models import Appointment
from appointments.utils.constants import AppointmentStatus
from core.utils.constants import AppointmentModes
from integrations.communications.outbox import (
    MAX_OUTBOX_ATTEMPTS,
    STALE_SENDING_MINUTES,
    apply_whatsapp_status_update,
    enqueue_appointment_message,
    process_outbox_message,
    reclaim_stale_sending_messages,
)
from integrations.models import CommunicationOutbox, CommunicationWebhookEvent
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
)
from programs.services.models import Service
from programs.services.utils.constants import ServiceCategory

UTC = ZoneInfo("UTC")


def create_appointment():
    center = Center.objects.create(name="Outbox Center", code="CT-OBX")
    user = User.objects.create_user(
        email="outbox-customer@example.com",
        phone="+91-9876543210",
    )
    customer = Customer.objects.create(user=user, contact_email=user.email)
    profile = CustomerProfile.objects.create(
        customer=customer,
        first_name="Out",
        last_name="Box",
        is_main=True,
    )
    service = Service.objects.create(
        name="Outbox Service QA",
        service_category=ServiceCategory.CONSULTATION,
    )
    start = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    end = start + timedelta(minutes=30)
    appointment = Appointment.objects.create(
        center=center,
        code="APT-OBX-001",
        customer_profile=profile,
        service=service,
        modality=AppointmentModes.VIRTUAL,
        start_datetime=start,
        end_datetime=end,
        duration_minutes=30,
        exclusive_start_datetime=start,
        exclusive_end_datetime=end,
        status=AppointmentStatus.CONFIRMED,
    )
    return appointment


class WhatsAppOutboxReclaimTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()

    def test_stale_sending_reclaimed_as_skipped_not_failed(self):
        stale_at = timezone.now() - timedelta(minutes=STALE_SENDING_MINUTES + 1)
        message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=CommunicationEventType.APPOINTMENT_CONFIRMED,
            to_phone="919876543210",
            template_name="appointment_confirmed",
            template_language="en",
            status=CommunicationOutboxStatus.SENDING,
            attempt_count=1,
        )
        CommunicationOutbox.objects.filter(pk=message.pk).update(updated_at=stale_at)
        updated = reclaim_stale_sending_messages()
        self.assertEqual(updated, 1)
        message.refresh_from_db()
        self.assertEqual(message.status, CommunicationOutboxStatus.SKIPPED)
        self.assertEqual(message.error_code, "stale_sending")
        self.assertIn("not retried", message.skip_reason)

    def test_fresh_sending_not_reclaimed(self):
        message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=CommunicationEventType.APPOINTMENT_CANCELLED,
            to_phone="919876543210",
            template_name="appointment_cancelled",
            template_language="en",
            status=CommunicationOutboxStatus.SENDING,
            attempt_count=1,
        )
        updated = reclaim_stale_sending_messages()
        self.assertEqual(updated, 0)
        message.refresh_from_db()
        self.assertEqual(message.status, CommunicationOutboxStatus.SENDING)


class WhatsAppWebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()
        self.message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=CommunicationEventType.APPOINTMENT_CONFIRMED,
            to_phone="919876543210",
            template_name="appointment_confirmed",
            template_language="en",
            status=CommunicationOutboxStatus.ACCEPTED,
            wamid="wamid.test.1",
        )

    def test_duplicate_webhook_event_is_noop(self):
        payload = {
            "id": "wamid.test.1",
            "status": "delivered",
            "timestamp": "1710000000",
        }
        first = apply_whatsapp_status_update(payload)
        self.assertIsNotNone(first)
        second = apply_whatsapp_status_update(payload)
        self.assertIsNone(second)
        self.assertEqual(
            CommunicationWebhookEvent.objects.filter(
                event_key="wamid.test.1:delivered:1710000000"
            ).count(),
            1,
        )
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, CommunicationOutboxStatus.DELIVERED)


class CommunicationOutboxEnqueueTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="token",
        WHATSAPP_PHONE_NUMBER_ID="123",
        GOOGLE_CALENDAR_ID="care@biopeak.health",
        COMMUNICATION_OUTBOX_WAKE_QUEUE_URL="",
    )
    @patch("integrations.communications.outbox.publish_outbox_wake")
    def test_enqueue_creates_whatsapp_and_google_pending_rows(self, mock_wake):
        whatsapp_message, google_message = enqueue_appointment_message(
            self.appointment,
            CommunicationEventType.APPOINTMENT_CONFIRMED,
        )
        self.assertEqual(whatsapp_message.channel, CommunicationChannel.WHATSAPP)
        self.assertEqual(whatsapp_message.status, CommunicationOutboxStatus.PENDING)
        self.assertEqual(
            google_message.channel, CommunicationChannel.GOOGLE_CALENDAR
        )
        self.assertEqual(google_message.status, CommunicationOutboxStatus.PENDING)
        mock_wake.assert_called_once()
        self.assertEqual(
            CommunicationOutbox.objects.filter(appointment=self.appointment).count(),
            2,
        )

    @override_settings(
        WHATSAPP_ACCESS_TOKEN="token",
        WHATSAPP_PHONE_NUMBER_ID="123",
        GOOGLE_CALENDAR_ID="care@biopeak.health",
        COMMUNICATION_OUTBOX_WAKE_QUEUE_URL="",
    )
    @patch("integrations.communications.outbox.publish_outbox_wake")
    def test_google_coalesces_open_row_for_same_appointment(self, mock_wake):
        first_whatsapp, first_google = enqueue_appointment_message(
            self.appointment,
            CommunicationEventType.APPOINTMENT_CONFIRMED,
        )
        second_whatsapp, second_google = enqueue_appointment_message(
            self.appointment,
            CommunicationEventType.APPOINTMENT_RESCHEDULED,
        )
        self.assertEqual(first_google.pk, second_google.pk)
        self.assertNotEqual(first_whatsapp.pk, second_whatsapp.pk)
        self.assertEqual(
            CommunicationOutbox.objects.filter(
                appointment=self.appointment,
                channel=CommunicationChannel.GOOGLE_CALENDAR,
            ).count(),
            1,
        )
        self.assertEqual(mock_wake.call_count, 2)


class GoogleOutboxReclaimTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()

    def test_stale_google_sending_reclaimed_as_failed(self):
        stale_at = timezone.now() - timedelta(minutes=STALE_SENDING_MINUTES + 1)
        message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=CommunicationEventType.APPOINTMENT_CONFIRMED,
            status=CommunicationOutboxStatus.SENDING,
            attempt_count=1,
        )
        CommunicationOutbox.objects.filter(pk=message.pk).update(updated_at=stale_at)
        updated = reclaim_stale_sending_messages()
        self.assertEqual(updated, 1)
        message.refresh_from_db()
        self.assertEqual(message.status, CommunicationOutboxStatus.FAILED)
        self.assertEqual(message.error_code, "stale_sending")
        self.assertIn("retrying", message.error_detail)

    def test_exhausted_stale_google_sending_skipped(self):
        stale_at = timezone.now() - timedelta(minutes=STALE_SENDING_MINUTES + 1)
        message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=CommunicationEventType.APPOINTMENT_CONFIRMED,
            status=CommunicationOutboxStatus.SENDING,
            attempt_count=MAX_OUTBOX_ATTEMPTS,
        )
        CommunicationOutbox.objects.filter(pk=message.pk).update(updated_at=stale_at)
        reclaim_stale_sending_messages()
        message.refresh_from_db()
        self.assertEqual(message.status, CommunicationOutboxStatus.SKIPPED)


class GoogleOutboxProcessTests(TestCase):
    def setUp(self):
        self.appointment = create_appointment()
        self.message = CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=CommunicationEventType.APPOINTMENT_CONFIRMED,
            status=CommunicationOutboxStatus.PENDING,
        )

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch(
        "integrations.communications.outbox.sync_appointment_with_google",
        return_value=None,
    )
    def test_google_process_marks_accepted(self, mock_sync):
        processed = process_outbox_message(self.message.pk)
        self.assertEqual(processed.status, CommunicationOutboxStatus.ACCEPTED)
        mock_sync.assert_called_once_with(self.appointment.pk)

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch(
        "integrations.communications.outbox.sync_appointment_with_google",
        return_value="Google Calendar organizer is disconnected",
    )
    def test_google_disconnected_is_retryable_failed(self, mock_sync):
        processed = process_outbox_message(self.message.pk)
        self.assertEqual(processed.status, CommunicationOutboxStatus.FAILED)
        self.assertEqual(processed.error_code, "organizer_disconnected")
        self.assertEqual(processed.attempt_count, 1)
        mock_sync.assert_called_once()

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch(
        "integrations.communications.outbox.sync_appointment_with_google",
        side_effect=ValueError("Failed to persist google_event_id"),
    )
    def test_google_persist_failure_is_retryable_failed(self, mock_sync):
        processed = process_outbox_message(self.message.pk)
        self.assertEqual(processed.status, CommunicationOutboxStatus.FAILED)
        self.assertEqual(processed.attempt_count, 1)
        mock_sync.assert_called_once()

    def test_google_waits_when_another_row_is_sending(self):
        CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=CommunicationEventType.APPOINTMENT_CANCELLED,
            status=CommunicationOutboxStatus.SENDING,
            attempt_count=1,
        )
        processed = process_outbox_message(self.message.pk)
        self.assertEqual(processed.status, CommunicationOutboxStatus.PENDING)
        self.assertEqual(processed.attempt_count, 0)

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch("integrations.communications.outbox.publish_outbox_wake")
    @patch(
        "integrations.communications.outbox.sync_appointment_with_google",
        return_value=None,
    )
    def test_google_wakes_remaining_row_for_same_appointment(
        self, mock_sync, mock_wake
    ):
        CommunicationOutbox.objects.create(
            appointment=self.appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=CommunicationEventType.APPOINTMENT_CANCELLED,
            status=CommunicationOutboxStatus.PENDING,
        )
        process_outbox_message(self.message.pk)
        mock_sync.assert_called_once()
        mock_wake.assert_called_once()
