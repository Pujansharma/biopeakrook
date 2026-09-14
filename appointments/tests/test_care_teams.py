from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from appointments.serializers.care_teams import CenterCareTeamSerializer
from appointments.tests.test_roster import plain_error
from appointments.views.care_teams import CenterCareTeamListCreateView


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


def live_center_assignment(center, associate):
    return AssociateCenterAssignment.objects.filter(
        center=center,
        associate=associate,
    ).first()


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
        self.admin_user = User.objects.create_user(email="care-admin@example.com")
        UserAccount.objects.create(
            user=self.admin_user,
            account_type=UserType.ADMIN,
        )
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

    def _team_ids(self, members_live=None, active=None):
        query_params = {}
        if members_live is not None:
            query_params["members_live"] = members_live
        if active is not None:
            query_params["active"] = active
        request = APIRequestFactory().get("/", query_params)
        force_authenticate(request, user=self.admin_user)
        view = CenterCareTeamListCreateView()
        view.setup(request, center_id=self.center.pk)
        view.request = view.initialize_request(request)
        return set(view.get_queryset().values_list("pk", flat=True))

    def test_omit_returns_all_teams(self):
        self.assertEqual(
            self._team_ids(),
            {self.live_team.pk, self.broken_team.pk},
        )
        self.assertEqual(
            self._team_ids(members_live="junk"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_1_excludes_teams_with_inactive_mapped_role(self):
        self.assertEqual(self._team_ids(members_live="1"), {self.live_team.pk})

    def test_members_live_0_keeps_only_broken_teams(self):
        self.assertEqual(self._team_ids(members_live="0"), {self.broken_team.pk})

    def test_members_live_1_excludes_inactive_user_member(self):
        self.live_doctor.user.is_active = False
        self.live_doctor.user.save(update_fields=["is_active"])
        self.assertEqual(self._team_ids(members_live="1"), set())
        self.assertEqual(
            self._team_ids(members_live="0"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_1_excludes_inactive_assignment(self):
        assignment = live_center_assignment(self.center, self.live_doctor)
        assignment.is_active = False
        assignment.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self._team_ids(members_live="1"), set())
        self.assertEqual(
            self._team_ids(members_live="0"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_1_excludes_inactive_role_link(self):
        role_link = AssociateCenterAssignmentRole.objects.filter(
            assignment=live_center_assignment(self.center, self.live_doctor),
            role=self.doctor_role,
        ).first()
        role_link.is_active = False
        role_link.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self._team_ids(members_live="1"), set())
        self.assertEqual(
            self._team_ids(members_live="0"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_1_excludes_unmapped_role(self):
        other_role = create_role(self.center, "Other Live Role")
        assign_roles(
            live_center_assignment(self.center, self.live_doctor),
            other_role,
        )
        self.assertEqual(self._team_ids(members_live="1"), set())
        self.assertEqual(
            self._team_ids(members_live="0"),
            {self.live_team.pk, self.broken_team.pk},
        )

    def test_members_live_independent_of_team_active(self):
        self.live_team.is_active = False
        self.live_team.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(
            self._team_ids(members_live="1"),
            {self.live_team.pk},
        )
        self.assertEqual(
            self._team_ids(members_live="1", active="1"),
            set(),
        )
        self.assertEqual(
            self._team_ids(members_live="1", active="0"),
            {self.live_team.pk},
        )
