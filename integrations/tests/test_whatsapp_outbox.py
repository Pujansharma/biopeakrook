from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from accounts.centers.models import Center
from accounts.customers.models import Customer, CustomerProfile
from accounts.users.models import User
from appointments.models import Appointment
from appointments.utils.constants import AppointmentStatus
from core.utils.constants import AppointmentModes
from integrations.communications.outbox import (
    STALE_SENDING_MINUTES,
    apply_whatsapp_status_update,
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
