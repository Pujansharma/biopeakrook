from datetime import time

from django.test import TestCase

from accounts.associates.models import Associate
from accounts.centers.models import Center
from accounts.users.models import User
from appointments.models import AssociateRosterEntry
from appointments.serializers import AssociateRosterBulkUpsertSerializer

MONDAY = "0"
TUESDAY = "1"
WEDNESDAY = "2"
START = time(9, 0)
END = time(17, 0)


def create_associate_and_center():
    user = User.objects.create_user(email="roster-associate@example.com")
    associate = Associate.objects.create(user=user)
    center = Center.objects.create(name="Roster Center", code="CT-RSTR")
    return associate, center


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
