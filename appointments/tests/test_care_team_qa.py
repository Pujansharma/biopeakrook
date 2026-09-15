from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.test import TestCase

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
from appointments.utils.constants import ExceptionSourceType
from appointments.utils.exceptions import appointment_filter_for_source
from appointments.utils.scheduling import (
    build_resolve_resource_pools,
)
from core.utils.constants import AppointmentModes
from programs.services.models import CenterServiceAssignment, Service
from programs.services.utils.constants import ServiceCategory

UTC = ZoneInfo("UTC")


def create_center(code="CT-QA"):
    return Center.objects.create(name=f"Center {code}", code=code)


def create_role(center, name):
    return AssociateRole.objects.create(center=center, name=name, is_active=True)


def assign_roles(assignment, *roles):
    AssociateCenterAssignmentRole.objects.filter(assignment=assignment).delete()
    AssociateCenterAssignmentRole.objects.bulk_create(
        [
            AssociateCenterAssignmentRole(assignment=assignment, role=role)
            for role in roles
            if role is not None
        ]
    )


def create_assigned_associate(center, email, role):
    user = User.objects.create_user(email=email)
    associate = Associate.objects.create(user=user)
    assignment = AssociateCenterAssignment.objects.create(
        associate=associate,
        center=center,
        is_active=True,
    )
    assign_roles(assignment, role)
    return associate


def create_care_team(center, doctor, doctor_role, coach, coach_role, name="Alpha"):
    serializer = CenterCareTeamSerializer(
        data={
            "name": name,
            "members": [
                {"associate_id": doctor.pk, "role_id": doctor_role.pk},
                {"associate_id": coach.pk, "role_id": coach_role.pk},
            ],
        },
        context={"center": center},
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(center=center)


class CareTeamDeactivateBlocksTests(TestCase):
    def setUp(self):
        self.center = create_center()
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.doctor = create_assigned_associate(
            self.center, "qa-doctor@example.com", self.doctor_role
        )
        self.coach = create_assigned_associate(
            self.center, "qa-coach@example.com", self.coach_role
        )
        self.care_team = create_care_team(
            self.center,
            self.doctor,
            self.doctor_role,
            self.coach,
            self.coach_role,
        )
        self.block = CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=self.care_team,
            is_recurring=False,
            start_datetime=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
            end_datetime=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
            is_active=True,
        )

    def test_deactivate_team_soft_deactivates_blocks(self):
        serializer = CenterCareTeamSerializer(
            instance=self.care_team,
            data={"is_active": False},
            partial=True,
            context={"center": self.center},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.block.refresh_from_db()
        self.care_team.refresh_from_db()
        self.assertFalse(self.care_team.is_active)
        self.assertFalse(self.block.is_active)

    def test_reactivate_team_does_not_revive_blocks(self):
        self.care_team.is_active = False
        self.care_team.save(update_fields=["is_active", "updated_at"])
        self.block.is_active = False
        self.block.save(update_fields=["is_active", "updated_at"])
        serializer = CenterCareTeamSerializer(
            instance=self.care_team,
            data={"is_active": True},
            partial=True,
            context={"center": self.center},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.block.refresh_from_db()
        self.assertTrue(self.care_team.is_active)
        self.assertFalse(self.block.is_active)


class CareTeamExceptionFilterTests(TestCase):
    def setUp(self):
        self.center = create_center("CT-EX")
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.doctor = create_assigned_associate(
            self.center, "ex-doctor@example.com", self.doctor_role
        )
        self.coach = create_assigned_associate(
            self.center, "ex-coach@example.com", self.coach_role
        )
        self.care_team = create_care_team(
            self.center,
            self.doctor,
            self.doctor_role,
            self.coach,
            self.coach_role,
            name="Exception Team",
        )
        self.block = CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=self.care_team,
            is_recurring=False,
            start_datetime=datetime(2026, 9, 11, 9, 0, tzinfo=UTC),
            end_datetime=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
            is_active=True,
        )

    def test_care_team_block_filter_is_team_stamped_only(self):
        query = appointment_filter_for_source(
            ExceptionSourceType.CARE_TEAM_BLOCK,
            self.block,
        )
        self.assertEqual(query, models.Q(care_team=self.care_team))


class CareTeamEmptyLiveMembersTests(TestCase):
    def setUp(self):
        self.center = create_center("CT-EMPTY")
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.doctor = create_assigned_associate(
            self.center, "empty-doctor@example.com", self.doctor_role
        )
        self.coach = create_assigned_associate(
            self.center, "empty-coach@example.com", self.coach_role
        )
        self.care_team = create_care_team(
            self.center,
            self.doctor,
            self.doctor_role,
            self.coach,
            self.coach_role,
            name="Empty Live",
        )
        AssociateCenterAssignment.objects.filter(center=self.center).update(
            is_active=False
        )
        self.service = Service.objects.create(
            name="Empty Live Service QA",
            service_category=ServiceCategory.CONSULTATION,
        )
        self.assignment = CenterServiceAssignment.objects.create(
            center=self.center,
            service=self.service,
            modality=AppointmentModes.VIRTUAL,
            duration=30,
            buffer_before=0,
            buffer_after=0,
            is_active=True,
        )

    def test_resolve_pools_rejects_empty_live_team(self):
        with self.assertRaises(DjangoValidationError) as raised:
            build_resolve_resource_pools(
                self.center,
                self.assignment,
                AppointmentModes.VIRTUAL,
                {"care_team_id": self.care_team.pk},
            )
        self.assertIn("no live members", str(raised.exception))
