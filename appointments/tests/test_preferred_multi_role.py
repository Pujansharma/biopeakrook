from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center
from accounts.users.models import User
from appointments.serializers.booking import normalize_preferred
from appointments.utils.scheduling import (
    HEALTH_COACH_ID_REJECT_MESSAGE,
    room_matches_assignment_types,
    validate_associate_assignments,
    validate_preferred_combo,
)
from core.utils.constants import AppointmentModes
from inventory.models import Room, RoomType
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoomTypeRequirement,
    Service,
)
from programs.services.utils.constants import ServiceCategory


def assign_roles(assignment, *roles):
    AssociateCenterAssignmentRole.objects.filter(assignment=assignment).delete()
    AssociateCenterAssignmentRole.objects.bulk_create(
        [
            AssociateCenterAssignmentRole(assignment=assignment, role=role)
            for role in roles
            if role is not None
        ]
    )


def create_center(code="PREF-1"):
    return Center.objects.create(name="Preferred Center", code=code)


def create_role(center, name):
    return AssociateRole.objects.create(center=center, name=name, is_active=True)


def create_assigned_associate(center, email, *roles):
    user = User.objects.create_user(email=email)
    associate = Associate.objects.create(user=user)
    assignment = AssociateCenterAssignment.objects.create(
        associate=associate,
        center=center,
        is_active=True,
        mode=AppointmentModes.BOTH,
    )
    assign_roles(assignment, *roles)
    return associate


class PreferredComboValidationTests(TestCase):
    def test_rejects_health_coach_id(self):
        with self.assertRaises(ValidationError) as raised:
            validate_preferred_combo(
                {"health_coach_id": "11111111-1111-1111-1111-111111111111"},
                AppointmentModes.VIRTUAL,
            )
        self.assertIn(HEALTH_COACH_ID_REJECT_MESSAGE, raised.exception.messages)

    def test_rejects_health_coach_id_in_normalize(self):
        with self.assertRaises(DRFValidationError) as raised:
            normalize_preferred(
                {"health_coach_id": "11111111-1111-1111-1111-111111111111"},
                modality=AppointmentModes.VIRTUAL,
                required=True,
            )
        self.assertIn(
            HEALTH_COACH_ID_REJECT_MESSAGE,
            str(raised.exception.detail),
        )

    def test_requires_room_for_in_person(self):
        with self.assertRaises(ValidationError):
            validate_preferred_combo(
                {"doctor_id": "11111111-1111-1111-1111-111111111111"},
                AppointmentModes.IN_PERSON,
            )

    def test_care_team_xor_specialty(self):
        with self.assertRaises(ValidationError):
            validate_preferred_combo(
                {
                    "care_team_id": "11111111-1111-1111-1111-111111111111",
                    "specialty_id": "22222222-2222-2222-2222-222222222222",
                },
                AppointmentModes.VIRTUAL,
            )

    def test_same_doctor_and_specialty_rejected(self):
        person = "11111111-1111-1111-1111-111111111111"
        with self.assertRaises(ValidationError):
            validate_preferred_combo(
                {"doctor_id": person, "specialty_id": person},
                AppointmentModes.VIRTUAL,
            )


class MultiRoleAssociatePinTests(TestCase):
    def setUp(self):
        self.center = create_center()
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.associate = create_assigned_associate(
            self.center,
            "multi@example.com",
            self.doctor_role,
            self.coach_role,
        )

    def test_pin_allows_either_held_role(self):
        validate_associate_assignments(
            self.center,
            [
                {
                    "role_id": str(self.coach_role.pk),
                    "associate_id": self.associate.pk,
                }
            ],
            role_requirements=[],
            modality=AppointmentModes.VIRTUAL,
        )

    def test_duplicate_associate_pin_rejected(self):
        with self.assertRaises(ValidationError):
            validate_associate_assignments(
                self.center,
                [
                    {
                        "role_id": str(self.doctor_role.pk),
                        "associate_id": self.associate.pk,
                    },
                    {
                        "role_id": str(self.coach_role.pk),
                        "associate_id": self.associate.pk,
                    },
                ],
                role_requirements=[],
                modality=AppointmentModes.VIRTUAL,
            )


class MultiRoomTypeRequirementTests(TestCase):
    def setUp(self):
        self.center = create_center("ROOM-1")
        self.room_type_a = RoomType.objects.create(
            center=self.center, name="Consult A", is_active=True
        )
        self.room_type_b = RoomType.objects.create(
            center=self.center, name="Consult B", is_active=True
        )
        self.service = Service.objects.create(
            name="Multi Room Service",
            service_category=ServiceCategory.CONSULTATION,
        )
        self.assignment = CenterServiceAssignment.objects.create(
            center=self.center,
            service=self.service,
            duration=30,
            modality=AppointmentModes.IN_PERSON,
            is_active=True,
        )
        CenterServiceRoomTypeRequirement.objects.bulk_create(
            [
                CenterServiceRoomTypeRequirement(
                    assignment=self.assignment,
                    room_type=self.room_type_a,
                ),
                CenterServiceRoomTypeRequirement(
                    assignment=self.assignment,
                    room_type=self.room_type_b,
                ),
            ]
        )

    def test_room_matches_any_required_type(self):
        room = Room(
            center=self.center,
            name="Room B",
            code="RB-1",
            room_type_ref=self.room_type_b,
            is_active=True,
        )
        room.save()
        self.assertTrue(room_matches_assignment_types(self.assignment, room))
