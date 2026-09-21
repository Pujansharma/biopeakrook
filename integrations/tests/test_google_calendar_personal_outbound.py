from datetime import time, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import AvailabilityOrigin, LeaveScope
from integrations.communications.outbox import (
    enqueue_associate_block_sync,
    enqueue_associate_leave_sync,
    process_google_outbox_message,
)
from integrations.google_calendar.personal_outbound import (
    build_weekly_rrule,
    personal_google_event_id,
    sync_associate_blocks_to_personal_google,
)
from integrations.models import CommunicationOutbox, GoogleCalendarConnection
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
)


def create_associate_with_center():
    center = Center.objects.create(name="Outbound Center", code="CT-OUT")
    user = User.objects.create_user(email="outbound-associate@example.com")
    UserAccount.objects.create(user=user, account_type=UserType.ASSOCIATE)
    associate = Associate.objects.create(user=user)
    AssociateCenterAssignment.objects.create(
        associate=associate, center=center, is_active=True
    )
    return center, associate


def connect_personal_google(user):
    return GoogleCalendarConnection.objects.create(
        user=user,
        google_email=user.email,
        google_refresh_token="enc:refresh",
        google_access_token="enc:access",
        is_active=True,
    )


class PersonalOutboundHelperTests(TestCase):
    def test_personal_event_id_from_series(self):
        series_id = uuid4()
        self.assertEqual(personal_google_event_id(series_id=series_id), series_id.hex)

    def test_weekly_rrule_maps_days(self):
        rules = build_weekly_rrule(["0", "2", "4"], None, time(14, 0))
        self.assertEqual(rules, ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"])


class AssociateBlockOutboundTests(TestCase):
    def setUp(self):
        self.center, self.associate = create_associate_with_center()

    def test_enqueue_one_off_block(self):
        start = timezone.localtime(timezone.now()) + timedelta(days=1)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            reason="Lunch",
            origin=AvailabilityOrigin.MANUAL,
        )
        message = enqueue_associate_block_sync(block=block)
        self.assertEqual(message.channel, CommunicationChannel.GOOGLE_CALENDAR)
        self.assertEqual(
            message.event_type, CommunicationEventType.ASSOCIATE_BLOCK_SYNC
        )
        self.assertEqual(message.associate_availability_block_id, block.pk)
        self.assertIsNone(message.appointment_id)

    def test_enqueue_coalesces_open_row(self):
        start = timezone.localtime(timezone.now()) + timedelta(days=1)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            origin=AvailabilityOrigin.MANUAL,
        )
        first = enqueue_associate_block_sync(block=block)
        second = enqueue_associate_block_sync(block=block)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            CommunicationOutbox.objects.filter(
                associate_availability_block=block
            ).count(),
            1,
        )

    @patch(
        "integrations.google_calendar.personal_outbound.send_google_calendar_outbound_event"
    )
    def test_sync_skips_when_not_connected(self, mock_send):
        start = timezone.localtime(timezone.now()) + timedelta(days=1)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            origin=AvailabilityOrigin.MANUAL,
        )
        skip_reason = sync_associate_blocks_to_personal_google(block_id=block.pk)
        self.assertEqual(skip_reason, "Personal Google Calendar not connected")
        mock_send.assert_not_called()

    @patch(
        "integrations.google_calendar.personal_outbound.send_google_calendar_outbound_event",
        return_value="google-event-1",
    )
    def test_sync_writes_event_when_connected(self, mock_send):
        connect_personal_google(self.associate.user)
        start = timezone.localtime(timezone.now()) + timedelta(days=1)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            reason="Focus",
            origin=AvailabilityOrigin.MANUAL,
        )
        skip_reason = sync_associate_blocks_to_personal_google(block_id=block.pk)
        self.assertIsNone(skip_reason)
        mock_send.assert_called_once()
        block.refresh_from_db()
        self.assertEqual(block.google_event_id, "google-event-1")

    def test_google_origin_not_written_back(self):
        connect_personal_google(self.associate.user)
        start = timezone.localtime(timezone.now()) + timedelta(days=1)
        block = AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            origin=AvailabilityOrigin.GOOGLE,
            google_event_id="from-google",
        )
        skip_reason = sync_associate_blocks_to_personal_google(block_id=block.pk)
        self.assertEqual(
            skip_reason,
            "Availability block was imported from Google; not written back",
        )

    @patch(
        "integrations.google_calendar.personal_outbound.send_google_calendar_outbound_event",
        return_value="series-event",
    )
    def test_recurring_series_builds_rrule(self, mock_send):
        connect_personal_google(self.associate.user)
        series_id = uuid4()
        effective_from = timezone.localdate() + timedelta(days=1)
        for day in ("0", "2"):
            AssociateAvailabilityBlock.objects.create(
                center=self.center,
                associate=self.associate,
                is_recurring=True,
                day_of_week=day,
                recurring_start_time=time(13, 0),
                recurring_end_time=time(14, 0),
                effective_from=effective_from,
                reason="Recurring lunch",
                origin=AvailabilityOrigin.MANUAL,
                series_id=series_id,
            )
        skip_reason = sync_associate_blocks_to_personal_google(series_id=series_id)
        self.assertIsNone(skip_reason)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(
            kwargs["recurrence"], ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]
        )
        self.assertEqual(
            AssociateAvailabilityBlock.objects.filter(
                series_id=series_id, google_event_id="series-event"
            ).count(),
            2,
        )


class AssociateLeaveOutboundTests(TestCase):
    def setUp(self):
        self.center, self.associate = create_associate_with_center()

    def test_enqueue_leave(self):
        start = timezone.localtime(timezone.now()) + timedelta(days=2)
        leave = AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.ALL_CENTERS,
            start_datetime=start,
            end_datetime=start + timedelta(days=1),
            reason="Holiday",
            origin=AvailabilityOrigin.MANUAL,
        )
        message = enqueue_associate_leave_sync(leave)
        self.assertEqual(message.associate_leave_id, leave.pk)
        self.assertEqual(
            message.event_type, CommunicationEventType.ASSOCIATE_LEAVE_SYNC
        )

    @patch(
        "integrations.google_calendar.personal_outbound.send_google_calendar_outbound_event",
        return_value="leave-event",
    )
    def test_process_outbox_leave_when_connected(self, mock_send):
        connect_personal_google(self.associate.user)
        start = timezone.localtime(timezone.now()) + timedelta(days=2)
        leave = AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.ALL_CENTERS,
            start_datetime=start,
            end_datetime=start + timedelta(hours=8),
            reason="Half day",
            origin=AvailabilityOrigin.MANUAL,
        )
        message = enqueue_associate_leave_sync(leave)
        message.status = CommunicationOutboxStatus.SENDING
        message.attempt_count = 1
        message.save(update_fields=["status", "attempt_count", "updated_at"])
        result = process_google_outbox_message(message)
        self.assertEqual(result.status, CommunicationOutboxStatus.ACCEPTED)
        leave.refresh_from_db()
        self.assertEqual(leave.google_event_id, "leave-event")

    def test_process_outbox_skips_when_not_connected(self):
        start = timezone.localtime(timezone.now()) + timedelta(days=2)
        leave = AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.ALL_CENTERS,
            start_datetime=start,
            end_datetime=start + timedelta(hours=8),
            origin=AvailabilityOrigin.MANUAL,
        )
        message = enqueue_associate_leave_sync(leave)
        message.status = CommunicationOutboxStatus.SENDING
        message.attempt_count = 1
        message.save(update_fields=["status", "attempt_count", "updated_at"])
        result = process_google_outbox_message(message)
        self.assertEqual(result.status, CommunicationOutboxStatus.SKIPPED)
        self.assertEqual(
            result.skip_reason, "Personal Google Calendar not connected"
        )
