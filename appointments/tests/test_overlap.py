from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from accounts.associates.models import Associate
from accounts.centers.models import Center
from accounts.users.models import User
from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.utils.constants import LeaveScope
from appointments.utils.overlap import (
    OVERLAP_ERROR,
    assert_associate_block_no_overlap,
    assert_associate_leave_no_overlap,
    assert_equipment_block_no_overlap,
    assert_equipment_downtime_no_overlap,
    assert_room_block_no_overlap,
    assert_room_downtime_no_overlap,
)
from inventory.models import Equipment, Room

UTC = ZoneInfo("UTC")
WINDOW_START = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
WINDOW_DATE = date(2026, 9, 7)
WINDOW_START_TIME = time(10, 0)
WINDOW_END_TIME = time(12, 0)


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


def create_center_room_and_equipment():
    center = Center.objects.create(name="Overlap Inventory Center", code="CT-INV")
    room = Room.objects.create(center=center, name="Overlap Room", code="RM-OVLP-0001")
    equipment = Equipment.objects.create(
        center=center,
        name="Overlap Equipment",
        code="EQ-OVLP-0001",
        serial_number="SN-OVLP-0001",
    )
    return center, room, equipment


def assert_room_one_off_block_no_overlap(room):
    assert_room_block_no_overlap(
        room,
        False,
        WINDOW_DATE,
        WINDOW_START_TIME,
        WINDOW_END_TIME,
        None,
        None,
        None,
        None,
        None,
    )


def assert_room_recurring_block_no_overlap(room):
    assert_room_block_no_overlap(
        room,
        True,
        None,
        None,
        None,
        "0",
        WINDOW_START_TIME,
        WINDOW_END_TIME,
        date(2026, 9, 1),
        None,
    )


def assert_equipment_one_off_block_no_overlap(equipment):
    assert_equipment_block_no_overlap(
        equipment,
        False,
        WINDOW_DATE,
        WINDOW_START_TIME,
        WINDOW_END_TIME,
        None,
        None,
        None,
        None,
        None,
    )


def assert_equipment_recurring_block_no_overlap(equipment):
    assert_equipment_block_no_overlap(
        equipment,
        True,
        None,
        None,
        None,
        "0",
        WINDOW_START_TIME,
        WINDOW_END_TIME,
        date(2026, 9, 1),
        None,
    )


class RoomDowntimeBlockOverlapTests(TestCase):
    def setUp(self):
        _, self.room, _ = create_center_room_and_equipment()

    def test_downtime_may_overlap_existing_one_off_block(self):
        RoomAvailabilityBlock.objects.create(
            room=self.room,
            is_recurring=False,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Training hold",
        )

        assert_room_downtime_no_overlap(
            self.room,
            WINDOW_DATE,
            WINDOW_START_TIME,
            WINDOW_END_TIME,
        )

    @override_settings(TIME_ZONE="UTC")
    def test_downtime_may_overlap_existing_recurring_block(self):
        RoomAvailabilityBlock.objects.create(
            room=self.room,
            is_recurring=True,
            day_of_week="0",
            recurring_start_time=WINDOW_START_TIME,
            recurring_end_time=WINDOW_END_TIME,
            effective_from=date(2026, 9, 1),
            reason="Weekly hold",
        )

        assert_room_downtime_no_overlap(
            self.room,
            WINDOW_DATE,
            WINDOW_START_TIME,
            WINDOW_END_TIME,
        )

    def test_one_off_block_cannot_overlap_existing_downtime(self):
        RoomDowntime.objects.create(
            room=self.room,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Renovation",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_room_one_off_block_no_overlap(self.room)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    @override_settings(TIME_ZONE="UTC")
    def test_recurring_block_cannot_overlap_existing_downtime(self):
        RoomDowntime.objects.create(
            room=self.room,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Renovation",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_room_recurring_block_no_overlap(self.room)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    def test_downtime_still_rejects_overlapping_downtime(self):
        RoomDowntime.objects.create(
            room=self.room,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="First downtime",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_room_downtime_no_overlap(
                self.room,
                WINDOW_DATE,
                WINDOW_START_TIME,
                WINDOW_END_TIME,
            )
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )


class EquipmentDowntimeBlockOverlapTests(TestCase):
    def setUp(self):
        _, _, self.equipment = create_center_room_and_equipment()

    def test_downtime_may_overlap_existing_one_off_block(self):
        EquipmentAvailabilityBlock.objects.create(
            equipment=self.equipment,
            is_recurring=False,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Training hold",
        )

        assert_equipment_downtime_no_overlap(
            self.equipment,
            WINDOW_DATE,
            WINDOW_START_TIME,
            WINDOW_END_TIME,
        )

    @override_settings(TIME_ZONE="UTC")
    def test_downtime_may_overlap_existing_recurring_block(self):
        EquipmentAvailabilityBlock.objects.create(
            equipment=self.equipment,
            is_recurring=True,
            day_of_week="0",
            recurring_start_time=WINDOW_START_TIME,
            recurring_end_time=WINDOW_END_TIME,
            effective_from=date(2026, 9, 1),
            reason="Weekly hold",
        )

        assert_equipment_downtime_no_overlap(
            self.equipment,
            WINDOW_DATE,
            WINDOW_START_TIME,
            WINDOW_END_TIME,
        )

    def test_one_off_block_cannot_overlap_existing_downtime(self):
        EquipmentDowntime.objects.create(
            equipment=self.equipment,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Maintenance",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_equipment_one_off_block_no_overlap(self.equipment)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    @override_settings(TIME_ZONE="UTC")
    def test_recurring_block_cannot_overlap_existing_downtime(self):
        EquipmentDowntime.objects.create(
            equipment=self.equipment,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="Maintenance",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_equipment_recurring_block_no_overlap(self.equipment)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    def test_downtime_still_rejects_overlapping_downtime(self):
        EquipmentDowntime.objects.create(
            equipment=self.equipment,
            date=WINDOW_DATE,
            start_time=WINDOW_START_TIME,
            end_time=WINDOW_END_TIME,
            reason="First downtime",
        )

        with self.assertRaises(ValidationError) as raised:
            assert_equipment_downtime_no_overlap(
                self.equipment,
                WINDOW_DATE,
                WINDOW_START_TIME,
                WINDOW_END_TIME,
            )
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )
