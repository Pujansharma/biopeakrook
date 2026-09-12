from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center
from accounts.users.models import User
from appointments.models import CareTeamAvailabilityBlock
from appointments.serializers.care_teams import CenterCareTeamSerializer
from appointments.utils.overlap import (
    CARE_TEAM_ONE_OFF_OVERLAP_CONSTRAINT,
    OVERLAP_ERROR,
    assert_care_team_block_no_overlap,
    raise_if_care_team_one_off_overlap_integrity,
)

UTC = ZoneInfo("UTC")
WINDOW_START = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def assign_roles(assignment, *roles):
    AssociateCenterAssignmentRole.objects.filter(assignment=assignment).delete()
    AssociateCenterAssignmentRole.objects.bulk_create(
        [
            AssociateCenterAssignmentRole(assignment=assignment, role=role)
            for role in roles
            if role is not None
        ]
    )


def create_team_fixture():
    center = Center.objects.create(name="Block Overlap Center", code="CT-BLK")
    doctor_role = AssociateRole.objects.create(
        center=center, name="Doctor", is_active=True
    )
    coach_role = AssociateRole.objects.create(
        center=center, name="Health Coach", is_active=True
    )
    doctor_user = User.objects.create_user(email="blk-doctor@example.com")
    coach_user = User.objects.create_user(email="blk-coach@example.com")
    doctor = Associate.objects.create(user=doctor_user)
    coach = Associate.objects.create(user=coach_user)
    assignment = AssociateCenterAssignment.objects.create(
        associate=doctor, center=center, is_active=True
    )
    assign_roles(assignment, doctor_role)
    assignment = AssociateCenterAssignment.objects.create(
        associate=coach, center=center, is_active=True
    )
    assign_roles(assignment, coach_role)
    serializer = CenterCareTeamSerializer(
        data={
            "name": "Block Team",
            "members": [
                {"associate_id": doctor.pk, "role_id": doctor_role.pk},
                {"associate_id": coach.pk, "role_id": coach_role.pk},
            ],
        },
        context={"center": center},
    )
    serializer.is_valid(raise_exception=True)
    care_team = serializer.save(center=center)
    return center, care_team


class CareTeamBlockOverlapTests(TestCase):
    def setUp(self):
        self.center, self.care_team = create_team_fixture()

    def test_one_off_block_cannot_overlap_existing_one_off(self):
        CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=self.care_team,
            is_recurring=False,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            is_active=True,
        )
        with self.assertRaises(ValidationError) as raised:
            assert_care_team_block_no_overlap(
                self.center,
                self.care_team,
                False,
                WINDOW_START + timedelta(hours=1),
                WINDOW_END + timedelta(hours=1),
                None,
                None,
                None,
                None,
                None,
            )
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    def test_integrity_helper_maps_exclusion_constraint(self):
        error = IntegrityError(
            f'duplicate key value violates exclusion constraint "{CARE_TEAM_ONE_OFF_OVERLAP_CONSTRAINT}"'
        )
        with self.assertRaises(ValidationError) as raised:
            raise_if_care_team_one_off_overlap_integrity(error)
        self.assertEqual(
            raised.exception.detail["non_field_errors"],
            [OVERLAP_ERROR],
        )

    def test_integrity_helper_rethrows_unrelated(self):
        error = IntegrityError("other_constraint")
        with self.assertRaises(IntegrityError):
            raise_if_care_team_one_off_overlap_integrity(error)

    def test_non_overlapping_one_off_allowed(self):
        CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=self.care_team,
            is_recurring=False,
            start_datetime=WINDOW_START,
            end_datetime=WINDOW_END,
            is_active=True,
        )
        assert_care_team_block_no_overlap(
            self.center,
            self.care_team,
            False,
            WINDOW_END,
            WINDOW_END + timedelta(hours=2),
            None,
            None,
            None,
            None,
            None,
        )

    def test_recurring_day_overlap_rejected(self):
        CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=self.care_team,
            is_recurring=True,
            day_of_week="1",
            recurring_start_time=time(10, 0),
            recurring_end_time=time(12, 0),
            effective_from=date(2026, 9, 1),
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            assert_care_team_block_no_overlap(
                self.center,
                self.care_team,
                True,
                None,
                None,
                "1",
                time(11, 0),
                time(13, 0),
                date(2026, 9, 1),
                None,
            )
