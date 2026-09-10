from datetime import time

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.associates.models import Associate
from accounts.centers.models import Center, CenterOperatingHour
from accounts.users.models import User
from appointments.models import AssociateRosterEntry
from appointments.serializers import AssociateRosterBulkUpsertSerializer

MONDAY = "0"
TUESDAY = "1"
WEDNESDAY = "2"
SUNDAY = "6"
START = time(9, 0)
END = time(17, 0)
OPEN = time(9, 0)
CLOSE = time(18, 0)


def plain_error(value):
    if isinstance(value, list):
        return [plain_error(item) for item in value]
    if isinstance(value, dict):
        return {key: plain_error(item) for key, item in value.items()}
    return str(value)


def create_associate_and_center():
    user = User.objects.create_user(email="roster-associate@example.com")
    associate = Associate.objects.create(user=user)
    center = Center.objects.create(name="Roster Center", code="CT-RSTR")
    seed_weekday_hours(center)
    return associate, center


def seed_weekday_hours(center):
    for day_of_week in ["0", "1", "2", "3", "4", "5"]:
        CenterOperatingHour.objects.create(
            center=center,
            day_of_week=day_of_week,
            is_open=True,
            open_time=OPEN,
            close_time=CLOSE,
            is_active=True,
        )
    CenterOperatingHour.objects.create(
        center=center,
        day_of_week=SUNDAY,
        is_open=False,
        open_time=None,
        close_time=None,
        is_active=True,
    )


def create_roster_day(center, associate, day_of_week):
    return AssociateRosterEntry.objects.create(
        center=center,
        associate=associate,
        day_of_week=day_of_week,
        start_time=START,
        end_time=END,
        is_active=True,
    )


def save_roster(center, associate, days, replace_unlisted=False):
    serializer = AssociateRosterBulkUpsertSerializer(
        data={
            "entries": [
                {
                    "day_of_week": int(day_of_week),
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                }
                for day_of_week in days
            ]
        }
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(
        center=center,
        associate=associate,
        replace_unlisted=replace_unlisted,
    )


def is_day_active(center, associate, day_of_week):
    roster_entry = AssociateRosterEntry.objects.filter(
        center=center,
        associate=associate,
        day_of_week=day_of_week,
        is_active=True,
    ).first()
    return roster_entry is not None


class AssociateRosterReplaceTests(TestCase):
    def setUp(self):
        self.associate, self.center = create_associate_and_center()
        create_roster_day(self.center, self.associate, MONDAY)
        create_roster_day(self.center, self.associate, TUESDAY)
        create_roster_day(self.center, self.associate, WEDNESDAY)

    def test_patch_omitted_day_is_deactivated(self):
        save_roster(
            self.center,
            self.associate,
            [MONDAY, TUESDAY],
            replace_unlisted=True,
        )

        self.assertTrue(is_day_active(self.center, self.associate, MONDAY))
        self.assertTrue(is_day_active(self.center, self.associate, TUESDAY))
        self.assertFalse(is_day_active(self.center, self.associate, WEDNESDAY))

    def test_post_omitted_day_stays_active(self):
        save_roster(
            self.center,
            self.associate,
            [MONDAY, TUESDAY],
            replace_unlisted=False,
        )

        self.assertTrue(is_day_active(self.center, self.associate, WEDNESDAY))


def save_roster_entries(center, associate, entries, replace_unlisted=False):
    serializer = AssociateRosterBulkUpsertSerializer(data={"entries": entries})
    serializer.is_valid(raise_exception=True)
    return serializer.save(
        center=center,
        associate=associate,
        replace_unlisted=replace_unlisted,
    )


def roster_hours_error_payload(test_case, center, associate, entries):
    with test_case.assertRaises(ValidationError) as raised:
        save_roster_entries(center, associate, entries)
    return plain_error(raised.exception.detail)


class AssociateRosterHoursValidationTests(TestCase):
    def setUp(self):
        self.associate, self.center = create_associate_and_center()

    def test_accepts_hours_inside_center_window_including_edges(self):
        save_roster_entries(
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 0,
                    "start_time": "09:00:00",
                    "end_time": "18:00:00",
                }
            ],
        )
        self.assertTrue(is_day_active(self.center, self.associate, MONDAY))

    def test_rejects_start_before_opening(self):
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 1,
                    "start_time": "08:00:00",
                    "end_time": "17:00:00",
                }
            ],
        )
        self.assertEqual(
            payload["non_field_errors"],
            ["Roster must fall within center operating hours."],
        )
        self.assertEqual(
            payload["day_errors"],
            [
                {
                    "day_of_week": "1",
                    "day_of_week_name": "Tuesday",
                    "open_time": "09:00:00",
                    "close_time": "18:00:00",
                    "errors": [
                        {
                            "code": "before_opening",
                            "field": "start_time",
                            "message": "Starts before center opening time.",
                        }
                    ],
                }
            ],
        )
        self.assertFalse(is_day_active(self.center, self.associate, TUESDAY))

    def test_rejects_end_after_closing(self):
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 1,
                    "start_time": "09:00:00",
                    "end_time": "22:00:00",
                }
            ],
        )
        self.assertEqual(
            payload["day_errors"][0]["errors"],
            [
                {
                    "code": "after_closing",
                    "field": "end_time",
                    "message": "Ends after center closing time.",
                }
            ],
        )
        self.assertFalse(is_day_active(self.center, self.associate, TUESDAY))

    def test_rejects_before_opening_and_after_closing_on_same_day(self):
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 1,
                    "start_time": "08:00:00",
                    "end_time": "22:00:00",
                }
            ],
        )
        self.assertEqual(
            [item["code"] for item in payload["day_errors"][0]["errors"]],
            ["before_opening", "after_closing"],
        )

    def test_rejects_closed_day(self):
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 6,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                }
            ],
        )
        self.assertEqual(
            payload["day_errors"],
            [
                {
                    "day_of_week": "6",
                    "day_of_week_name": "Sunday",
                    "errors": [
                        {
                            "code": "center_closed",
                            "field": "day_of_week",
                            "message": "Center is closed on this day.",
                        }
                    ],
                }
            ],
        )

    def test_rejects_day_without_operating_hours(self):
        CenterOperatingHour.objects.filter(
            center=self.center, day_of_week=WEDNESDAY
        ).delete()
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 2,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                }
            ],
        )
        self.assertEqual(
            payload["day_errors"][0]["errors"][0]["code"],
            "center_hours_missing",
        )
        self.assertEqual(
            payload["day_errors"][0]["errors"][0]["field"],
            "day_of_week",
        )

    def test_collects_every_failing_day_and_saves_none(self):
        payload = roster_hours_error_payload(
            self,
            self.center,
            self.associate,
            [
                {
                    "day_of_week": 0,
                    "start_time": "08:00:00",
                    "end_time": "17:00:00",
                },
                {
                    "day_of_week": 1,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
                {
                    "day_of_week": 6,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                },
            ],
        )
        self.assertEqual(
            [day_error["day_of_week"] for day_error in payload["day_errors"]],
            ["0", "6"],
        )
        self.assertFalse(is_day_active(self.center, self.associate, MONDAY))
        self.assertFalse(is_day_active(self.center, self.associate, TUESDAY))
        self.assertFalse(is_day_active(self.center, self.associate, SUNDAY))
