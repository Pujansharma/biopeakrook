from django.test import TestCase

from accounts.centers.models import Center
from accounts.centers.utils.db import generate_equipment_code, generate_room_code


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
