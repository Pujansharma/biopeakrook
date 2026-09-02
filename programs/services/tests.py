from django.test import TestCase
from rest_framework.exceptions import ValidationError

from programs.services.models import Service
from programs.services.serializers import ServiceSerializer
from programs.services.utils.constants import ServiceCategory


def plain_error(value):
    if isinstance(value, list):
        return [plain_error(item) for item in value]
    if isinstance(value, dict):
        return {key: plain_error(item) for key, item in value.items()}
    return str(value)


def create_service(name="IR Sauna"):
    return Service.objects.create(
        name=name,
        service_category=ServiceCategory.THERAPY,
        is_global=True,
    )


def service_payload(name="IR Sauna"):
    return {
        "name": name,
        "service_category": ServiceCategory.THERAPY,
        "is_global": True,
    }


def validate_service(payload, instance=None, partial=False):
    serializer = ServiceSerializer(instance=instance, data=payload, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer


def service_error_payload(test_case, payload, instance=None, partial=False):
    with test_case.assertRaises(ValidationError) as raised:
        validate_service(payload, instance=instance, partial=partial)
    return plain_error(raised.exception.detail)


class ServiceNameUniquenessTests(TestCase):
    def test_rejects_duplicate_name_on_create(self):
        create_service()
        payload = service_error_payload(self, service_payload())
        self.assertEqual(
            payload["name"],
            ["A service with this name already exists."],
        )

    def test_rejects_duplicate_name_case_insensitive(self):
        create_service()
        payload = service_error_payload(self, service_payload(name="ir sauna"))
        self.assertEqual(
            payload["name"],
            ["A service with this name already exists."],
        )

    def test_rejects_rename_to_existing_name(self):
        create_service()
        other = create_service(name="Red Light")
        payload = service_error_payload(
            self,
            {"name": "IR Sauna"},
            instance=other,
            partial=True,
        )
        self.assertEqual(
            payload["name"],
            ["A service with this name already exists."],
        )

    def test_allows_same_name_on_self_update(self):
        service = create_service()
        serializer = validate_service(
            {"name": "IR Sauna"},
            instance=service,
            partial=True,
        )
        self.assertEqual(serializer.validated_data["name"], "IR Sauna")
