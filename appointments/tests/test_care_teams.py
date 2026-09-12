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
from appointments.serializers.care_teams import CenterCareTeamSerializer
from appointments.tests.test_roster import plain_error


def create_center():
    return Center.objects.create(name="Care Team Center", code="CT-CARE")


def create_role(center, name, is_active=True):
    return AssociateRole.objects.create(
        center=center,
        name=name,
        is_active=is_active,
    )


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


def members_payload(first_associate, first_role, second_associate, second_role):
    return [
        {
            "associate_id": first_associate.pk,
            "role_id": first_role.pk,
        },
        {
            "associate_id": second_associate.pk,
            "role_id": second_role.pk,
        },
    ]


def validate_care_team(center, members, name="Alpha"):
    serializer = CenterCareTeamSerializer(
        data={"name": name, "members": members},
        context={"center": center},
    )
    serializer.is_valid(raise_exception=True)
    return serializer


def care_team_error_payload(test_case, center, members, name="Alpha"):
    with test_case.assertRaises(ValidationError) as raised:
        validate_care_team(center, members, name=name)
    return plain_error(raised.exception.detail)


class CareTeamInactiveRoleTests(TestCase):
    def setUp(self):
        self.center = create_center()
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.doctor = create_assigned_associate(
            self.center, "care-doctor@example.com", self.doctor_role
        )
        self.coach = create_assigned_associate(
            self.center, "care-coach@example.com", self.coach_role
        )

    def test_rejects_inactive_role_on_create(self):
        self.doctor_role.is_active = False
        self.doctor_role.save(update_fields=["is_active", "updated_at"])
        payload = care_team_error_payload(
            self,
            self.center,
            members_payload(
                self.doctor, self.doctor_role, self.coach, self.coach_role
            ),
        )
        self.assertEqual(payload["members"], ["Role is inactive."])

    def test_keeps_assignment_error_when_role_is_active(self):
        payload = care_team_error_payload(
            self,
            self.center,
            members_payload(
                self.doctor, self.coach_role, self.coach, self.doctor_role
            ),
        )
        self.assertEqual(
            payload["members"],
            [
                "Associate is not assigned to this center with the required role."
            ],
        )

    def test_accepts_active_roles_on_create(self):
        serializer = validate_care_team(
            self.center,
            members_payload(
                self.doctor, self.doctor_role, self.coach, self.coach_role
            ),
        )
        care_team = serializer.save(center=self.center)
        self.assertEqual(care_team.members_count, 2)
