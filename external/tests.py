from django.test import TestCase
from rest_framework.test import APIRequestFactory

from accounts.centers.models import Center
from accounts.customers.tests import add_therapy_service, create_customer_profile
from external.views import (
    ExternalUserProgramServiceDetailView,
    ExternalUserProgramServicesListView,
)
from programs.models import Program, TherapyProgram
from programs.services.models import CenterServiceAssignment, Service
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType

OWNER_PHONE = "+91-9876543210"
OTHER_PHONE = "+91-9123456780"


def get_program_services(program_pk, phone: str):
    request = APIRequestFactory().get(
        f"/external/customer-therapy-programs/{program_pk}/services/",
        {"phone": phone},
    )
    return ExternalUserProgramServicesListView.as_view()(request, pk=program_pk)


def get_program_service_detail(service_pk, phone: str):
    request = APIRequestFactory().get(
        f"/external/customer-therapy-services/{service_pk}/",
        {"phone": phone},
    )
    return ExternalUserProgramServiceDetailView.as_view()(request, pk=service_pk)


def center_ids(service_payload: dict) -> list[str]:
    return [center["id"] for center in service_payload["centers"]]


class TestExternalProgramServiceCenters(TestCase):
    def setUp(self):
        home_center = Center.objects.create(name="Home", code="X-HOME")
        self.redeemable_center = Center.objects.create(name="Redeemable", code="X-REDEEM")
        other_center = Center.objects.create(name="Other", code="X-OTHER")
        inactive_center = Center.objects.create(name="Inactive", code="X-INACT")
        service = Service.objects.create(
            name="Hyperbaric", service_category=ServiceCategory.THERAPY
        )
        CenterServiceAssignment.objects.create(
            service=service, center=self.redeemable_center
        )
        CenterServiceAssignment.objects.create(service=service, center=other_center)
        CenterServiceAssignment.objects.create(
            service=service, center=inactive_center, is_active=False
        )

        profile = create_customer_profile("phone-owner@example.com", OWNER_PHONE)
        create_customer_profile("phone-other@example.com", OTHER_PHONE)
        program = Program.objects.create(
            customer_profile=profile,
            center=home_center,
            program_type=ProgramType.THERAPY,
        )
        program.redeemable_centers.set([self.redeemable_center, inactive_center])
        self.therapy_program = TherapyProgram.objects.create(program=program)
        self.therapy_service = add_therapy_service(program, service)

    def test_list_returns_only_active_redeemable_centers(self):
        response = get_program_services(self.therapy_program.pk, "9876543210")

        self.assertEqual(response.status_code, 200)
        results = response.data["data"]
        self.assertEqual(len(results), 1)
        self.assertEqual(
            center_ids(results[0]["service"]), [str(self.redeemable_center.pk)]
        )

    def test_list_is_empty_for_another_phone(self):
        response = get_program_services(self.therapy_program.pk, "9123456780")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [])

    def test_detail_returns_only_active_redeemable_centers(self):
        response = get_program_service_detail(self.therapy_service.pk, "9876543210")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            center_ids(response.data["data"]["service"]),
            [str(self.redeemable_center.pk)],
        )

    def test_detail_404s_for_another_phone(self):
        response = get_program_service_detail(self.therapy_service.pk, "9123456780")

        self.assertEqual(response.status_code, 404)
