from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from accounts.associates.models import Associate
from accounts.centers.models import Center
from accounts.users.models import User
from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import LeaveScope
from appointments.utils.overlap import (
    OVERLAP_ERROR,
    assert_associate_block_no_overlap,
    assert_associate_leave_no_overlap,
)

UTC = ZoneInfo("UTC")
WINDOW_START = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def create_associate_and_center():
    user = User.objects.create_user(email="overlap-associate@example.com")
    associate = Associate.objects.create(user=user)
    center = Center.objects.create(name="Overlap Center", code="CT-OVLP")
    return associate, center


def assert_one_off_block_no_overlap(center, associate, start_datetime, end_datetime):
    assert_associate_block_no_overlap(
        center,
        associate,
        False,
        start_datetime,
        end_datetime,
        None,
        None,
        None,
        None,
        None,
    )


def assert_recurring_block_no_overlap(center, associate):
    assert_associate_block_no_overlap(
        center,
        associate,
        True,
        None,
        None,
        "0",
        time(10, 0),
        time(12, 0),
        date(2026, 9, 1),
        None,
    )


class AssociateLeaveBlockOverlapTests(TestCase):
    def setUp(self):
        self.associate, self.center = create_associate_and_center()

    def test_leave_may_overlap_existing_one_off_block(self):
        AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=False,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            reason="Admin block",
        )

        assert_associate_leave_no_overlap(
            self.associate,
            LeaveScope.CENTER,
            self.center,
            WINDOW_START,
            WINDOW_END,
        )

    @override_settings(TIME_ZONE="UTC")
    def test_leave_may_overlap_existing_recurring_block(self):
        AssociateAvailabilityBlock.objects.create(
            center=self.center,
            associate=self.associate,
            is_recurring=True,
            day_of_week="0",
            recurring_start_time=time(10, 0),
            recurring_end_time=time(12, 0),
            effective_from=date(2026, 9, 1),
            reason="Weekly admin",
        )

        assert_associate_leave_no_overlap(
            self.associate,
            LeaveScope.CENTER,
            self.center,
            WINDOW_START,
            WINDOW_END,
        )

    def test_one_off_block_cannot_overlap_existing_leave(self):
        AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            reason="Personal leave",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_one_off_block_no_overlap(
                self.center,
                self.associate,
                WINDOW_START,
                WINDOW_END,
            )
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    @override_settings(TIME_ZONE="UTC")
    def test_recurring_block_cannot_overlap_existing_leave(self):
        AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            reason="Personal leave",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_recurring_block_no_overlap(self.center, self.associate)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    def test_leave_still_rejects_overlapping_leave(self):
        AssociateLeave.objects.create(
            associate=self.associate,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            reason="First leave",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_associate_leave_no_overlap(
                self.associate,
                LeaveScope.CENTER,
                self.center,
                WINDOW_START,
                WINDOW_END,
            )
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )
