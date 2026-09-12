from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.admins.utils.db import create_admin_user
from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center
from accounts.centers.utils.db import generate_equipment_code, generate_room_code
from accounts.centers.views import CenterAssociateListView
from accounts.users.models import User


class ResourceCodeTests(TestCase):
    def test_equipment_codes_include_center_code_and_differ_across_centers(self):
        first_center = Center.objects.create(name="First Center", code="CT-0001")
        second_center = Center.objects.create(name="Second Center", code="CT-0002")

        first_code = generate_equipment_code(first_center.pk)
        second_code = generate_equipment_code(second_center.pk)

        self.assertEqual(first_code, "EQ-CT-0001-0001")
        self.assertEqual(second_code, "EQ-CT-0002-0001")
        self.assertNotEqual(first_code, second_code)

    def test_room_codes_include_center_code_and_differ_across_centers(self):
        first_center = Center.objects.create(name="First Center", code="CT-0001")
        second_center = Center.objects.create(name="Second Center", code="CT-0002")

        first_code = generate_room_code(first_center.pk)
        second_code = generate_room_code(second_center.pk)

        self.assertEqual(first_code, "RM-CT-0001-0001")
        self.assertEqual(second_code, "RM-CT-0002-0001")
        self.assertNotEqual(first_code, second_code)

    def test_equipment_code_does_not_match_legacy_global_eq_format(self):
        center = Center.objects.create(name="Legacy Collision Center", code="CT-0001")
        generated_code = generate_equipment_code(center.pk)
        self.assertNotEqual(generated_code, "EQ-0001")
        self.assertLessEqual(len(generated_code), 20)


class CenterAssociateListDedupTests(TestCase):
    def setUp(self):
        self.admin = create_admin_user(
            "center-admin@example.com", password="securepassword123"
        )
        self.center = Center.objects.create(name="Multi Role Center", code="CT-MROLE")
        doctor_role = AssociateRole.objects.create(
            center=self.center, name="Doctor", is_active=True
        )
        coach_role = AssociateRole.objects.create(
            center=self.center, name="Health Coach", is_active=True
        )
        associate_user = User.objects.create_user(email="multi-role@example.com")
        associate = Associate.objects.create(user=associate_user)
        assignment = AssociateCenterAssignment.objects.create(
            associate=associate,
            center=self.center,
            is_care_staff=True,
        )
        AssociateCenterAssignmentRole.objects.bulk_create(
            [
                AssociateCenterAssignmentRole(assignment=assignment, role=doctor_role),
                AssociateCenterAssignmentRole(assignment=assignment, role=coach_role),
            ]
        )
        self.associate_user_id = str(associate_user.pk)
        self.factory = APIRequestFactory()

    def test_role_filter_does_not_duplicate_multi_role_associate(self):
        request = self.factory.get(
            f"/centers/{self.center.pk}/associates/", {"role": "1"}
        )
        force_authenticate(request, user=self.admin.user)
        response = CenterAssociateListView.as_view()(request, pk=self.center.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["data"]
        matching_ids = [
            row["id"] for row in rows if str(row["id"]) == self.associate_user_id
        ]
        self.assertEqual(len(matching_ids), 1)
        self.assertEqual(response.data["count"], 1)

