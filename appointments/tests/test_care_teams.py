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
from appointments.models import CenterCareTeam
from appointments.serializers.care_teams import CenterCareTeamSerializer
from appointments.tests.test_roster import plain_error
from appointments.utils.care_teams import members_live_filter


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


class CareTeamMembersLiveFilterTests(TestCase):
    def setUp(self):
        self.center = create_center()
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.live_doctor = create_assigned_associate(
            self.center, "live-doctor@example.com", self.doctor_role
        )
        self.live_coach = create_assigned_associate(
            self.center, "live-coach@example.com", self.coach_role
        )
        self.live_team = validate_care_team(
            self.center,
            members_payload(
                self.live_doctor,
                self.doctor_role,
                self.live_coach,
                self.coach_role,
            ),
            name="Live Team",
        ).save(center=self.center)

        self.broken_doctor_role = create_role(self.center, "Broken Doctor")
        self.broken_coach_role = create_role(self.center, "Broken Coach")
        self.broken_doctor = create_assigned_associate(
            self.center, "broken-doctor@example.com", self.broken_doctor_role
        )
        self.broken_coach = create_assigned_associate(
            self.center, "broken-coach@example.com", self.broken_coach_role
        )
        self.broken_team = validate_care_team(
            self.center,
            members_payload(
                self.broken_doctor,
                self.broken_doctor_role,
                self.broken_coach,
                self.broken_coach_role,
            ),
            name="Broken Team",
        ).save(center=self.center)
        self.broken_doctor_role.is_active = False
        self.broken_doctor_role.save(update_fields=["is_active", "updated_at"])

    def _team_ids(self, query_value):
        return set(
            CenterCareTeam.objects.filter(
                center=self.center,
            )
            .filter(members_live_filter(query_value))
            .values_list("pk", flat=True)
        )

    def test_omit_returns_all_teams(self):
        self.assertEqual(
            self._team_ids(None),
            {self.live_team.pk, self.broken_team.pk},
        )
        self.assertEqual(
            self._team_ids("junk"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_1_excludes_teams_with_inactive_mapped_role(self):
        self.assertEqual(self._team_ids("1"), {self.live_team.pk})

    def test_members_live_0_keeps_only_broken_teams(self):
        self.assertEqual(self._team_ids("0"), {self.broken_team.pk})

    def test_members_live_1_excludes_inactive_user_member(self):
        self.live_doctor.user.is_active = False
        self.live_doctor.user.save(update_fields=["is_active"])
        self.assertEqual(self._team_ids("1"), set())
        self.assertEqual(
            self._team_ids("0"),
            {self.live_team.pk, self.broken_team.pk},
        )
