from datetime import time

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.associates.models import Associate
from accounts.centers.models import Center, CenterOperatingHour
from accounts.users.models import User
from appointments.models import AssociateRosterEntry
from appointments.serializers import CenterOperatingHoursBulkUpsertSerializer
from appointments.tests.test_roster import plain_error

MONDAY = "0"
TUESDAY = "1"
SUNDAY = "6"


def create_center_with_associate():
    user = User.objects.create_user(email="hours-associate@example.com")
    associate = Associate.objects.create(user=user)
    center = Center.objects.create(name="Hours Center", code="CT-HRS")
    return associate, center


def seed_open_days(center, day_values, open_time, close_time):
    for day_of_week in day_values:
        CenterOperatingHour.objects.create(
            center=center,
            day_of_week=day_of_week,
            is_open=True,
            open_time=open_time,
            close_time=close_time,
            is_active=True,
        )


def save_operating_hours(center, payload):
    serializer = CenterOperatingHoursBulkUpsertSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return serializer.save(center=center)


def operating_hours_error_payload(test_case, center, payload):
    with test_case.assertRaises(ValidationError) as raised:
        save_operating_hours(center, payload)
    return plain_error(raised.exception.detail)


class OperatingHoursRosterConflictTests(TestCase):
    def setUp(self):
        self.associate, self.center = create_center_with_associate()
        seed_open_days(
            self.center,
            [MONDAY, TUESDAY],
            time(9, 0),
            time(18, 0),
        )
        AssociateRosterEntry.objects.create(
            center=self.center,
            associate=self.associate,
            day_of_week=TUESDAY,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_active=True,
        )

    def test_accepts_hours_that_still_cover_roster(self):
        save_operating_hours(
            self.center,
            {
                "open_time": "09:00:00",
                "close_time": "17:00:00",
                "days": [TUESDAY],
            },
        )
        operating_hour = CenterOperatingHour.objects.filter(
            center=self.center,
            day_of_week=TUESDAY,
            is_active=True,
        ).first()
        self.assertEqual(operating_hour.close_time, time(17, 0))

    def test_rejects_narrower_window_than_active_roster(self):
        payload = operating_hours_error_payload(
            self,
            self.center,
            {
                "open_time": "10:00:00",
                "close_time": "16:00:00",
                "days": [TUESDAY],
            },
        )
        self.assertEqual(
            payload["non_field_errors"],
            ["Operating hours conflict with existing staff roster."],
        )
        tuesday = payload["day_errors"][0]
        self.assertEqual(tuesday["day_of_week"], "1")
        self.assertEqual(tuesday["day_of_week_name"], "Tuesday")
        self.assertEqual(tuesday["open_time"], "10:00:00")
        self.assertEqual(tuesday["close_time"], "16:00:00")
        self.assertEqual(
            tuesday["errors"],
            [
                {
                    "code": "before_opening",
                    "field": "open_time",
                    "message": "Active roster starts before the new opening time.",
                    "associate_ids": [str(self.associate.pk)],
                },
                {
                    "code": "after_closing",
                    "field": "close_time",
                    "message": "Active roster ends after the new closing time.",
                    "associate_ids": [str(self.associate.pk)],
                },
            ],
        )
        operating_hour = CenterOperatingHour.objects.filter(
            center=self.center,
            day_of_week=TUESDAY,
            is_active=True,
        ).first()
        self.assertEqual(operating_hour.open_time, time(9, 0))
        self.assertEqual(operating_hour.close_time, time(18, 0))

    def test_rejects_closing_a_day_with_active_roster(self):
        payload = operating_hours_error_payload(
            self,
            self.center,
            {"closed_days": [TUESDAY]},
        )
        self.assertEqual(
            payload["day_errors"],
            [
                {
                    "day_of_week": "1",
                    "day_of_week_name": "Tuesday",
                    "errors": [
                        {
                            "code": "roster_on_closed_day",
                            "field": "day_of_week",
                            "message": "Active roster exists on a day being closed.",
                            "associate_ids": [str(self.associate.pk)],
                        }
                    ],
                }
            ],
        )

    def test_ignores_inactive_roster_when_closing_a_day(self):
        AssociateRosterEntry.objects.filter(
            center=self.center, day_of_week=TUESDAY
        ).update(is_active=False)
        save_operating_hours(self.center, {"closed_days": [TUESDAY]})
        operating_hour = CenterOperatingHour.objects.filter(
            center=self.center,
            day_of_week=TUESDAY,
            is_active=True,
        ).first()
        self.assertFalse(operating_hour.is_open)
