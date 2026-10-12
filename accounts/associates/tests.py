from django.test import TestCase
from rest_framework.exceptions import ValidationError

from accounts.associates.models import AssociateRole
from accounts.associates.serializers import (
    ASSOCIATE_ROLE_NAME_CLASH,
    AssociateRoleSerializer,
)
from accounts.centers.models import Center


def plain_error(detail):
    if isinstance(detail, list):
        return [plain_error(item) for item in detail]
    if isinstance(detail, dict):
        return {key: plain_error(value) for key, value in detail.items()}
    return str(detail)


class AssociateRoleNameUniqueTests(TestCase):
    def setUp(self):
        self.center = Center.objects.create(name="Role Center", code="CT-ROLE")
        self.other_center = Center.objects.create(
            name="Other Role Center", code="CT-ROLE2"
        )

    def test_create_rejects_case_insensitive_duplicate(self):
        AssociateRole.objects.create(center=self.center, name="Doctor", is_active=True)
        serializer = AssociateRoleSerializer(
            data={"name": "doctor"},
            context={"center": self.center},
        )
        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            plain_error(serializer.errors),
            {"name": [ASSOCIATE_ROLE_NAME_CLASH]},
        )

    def test_update_rejects_rename_to_existing_name(self):
        doctor = AssociateRole.objects.create(
            center=self.center, name="Doctor", is_active=True
        )
        coach = AssociateRole.objects.create(
            center=self.center, name="Coach", is_active=True
        )
        serializer = AssociateRoleSerializer(
            coach,
            data={"name": "doctor"},
            partial=True,
            context={"center": self.center},
        )
        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            plain_error(serializer.errors),
            {"name": [ASSOCIATE_ROLE_NAME_CLASH]},
        )
        self.assertEqual(doctor.name, "Doctor")

    def test_update_allows_self_rename_different_case(self):
        doctor = AssociateRole.objects.create(
            center=self.center, name="Doctor", is_active=True
        )
        serializer = AssociateRoleSerializer(
            doctor,
            data={"name": "doctor"},
            partial=True,
            context={"center": self.center},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.name, "doctor")

    def test_same_name_allowed_across_centers(self):
        AssociateRole.objects.create(center=self.center, name="Doctor", is_active=True)
        serializer = AssociateRoleSerializer(
            data={"name": "Doctor"},
            context={"center": self.other_center},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        role = serializer.save(center=self.other_center)
        self.assertEqual(role.name, "Doctor")
        self.assertEqual(role.center_id, self.other_center.pk)

    def test_create_maps_integrity_error_to_validation_error(self):
        AssociateRole.objects.create(center=self.center, name="Doctor", is_active=True)
        serializer = AssociateRoleSerializer(context={"center": self.center})
        with self.assertRaises(ValidationError) as raised:
            serializer.create({"name": "doctor", "center": self.center})
        self.assertEqual(
            plain_error(raised.exception.detail),
            {"name": [ASSOCIATE_ROLE_NAME_CLASH]},
        )
