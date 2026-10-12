from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory

from accounts.centers.models import Center
from accounts.customers.models import Customer, CustomerProfile
from accounts.customers.programs.views import CustomerTherapyProgramServicesView
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from core.utils.authentication import get_tokens_for_user
from programs.models import Program, ProgramService, TherapyProgram, TherapyProgramService
from programs.services.models import CenterServiceAssignment, Service
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType


def create_customer_profile(email: str, phone: str | None = None) -> CustomerProfile:
    user = User.objects.create_user(email=email, phone=phone)
    UserAccount.objects.create(user=user, account_type=UserType.CUSTOMER)
    customer = Customer.objects.create(user=user, contact_email=email)
    return CustomerProfile.objects.create(
        customer=customer,
        first_name="Pat",
        last_name="Ient",
        is_main=True,
    )


def create_therapy_program(
    customer_profile: CustomerProfile,
    center: Center,
    service: Service,
    redeemable_centers: list[Center],
) -> TherapyProgram:
    program = Program.objects.create(
        customer_profile=customer_profile,
        center=center,
        program_type=ProgramType.THERAPY,
    )
    program.redeemable_centers.set(redeemable_centers)
    therapy_program = TherapyProgram.objects.create(program=program)
    add_therapy_service(program, service)
    return therapy_program


def add_therapy_service(program: Program, service: Service) -> TherapyProgramService:
    program_service = ProgramService.objects.create(program=program, service=service)
    return TherapyProgramService.objects.create(
        program_service=program_service, sessions_count=5
    )


def count_queries(user: User, profile_pk, program_pk) -> int:
    with CaptureQueriesContext(connection) as captured:
        get_therapy_program_services(user, profile_pk, program_pk)
    return len(captured)


def get_therapy_program_services(user: User, profile_pk, program_pk):
    access_token = get_tokens_for_user(user)["access"]
    request = APIRequestFactory().get(
        f"/profiles/{profile_pk}/programs/therapy-programs/{program_pk}/services/",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )
    view = CustomerTherapyProgramServicesView.as_view()
    return view(request, pk=profile_pk, program_pk=program_pk)


class TestCustomerTherapyProgramServicesView(TestCase):
    def setUp(self):
        self.home_center = Center.objects.create(name="Home", code="C-HOME")
        self.redeemable_center = Center.objects.create(name="Redeemable", code="C-REDEEM")
        self.other_center = Center.objects.create(name="Other", code="C-OTHER")
        self.inactive_center = Center.objects.create(name="Inactive", code="C-INACT")
        self.service = Service.objects.create(
            name="Cryotherapy", service_category=ServiceCategory.THERAPY
        )
        CenterServiceAssignment.objects.create(
            service=self.service, center=self.redeemable_center
        )
        CenterServiceAssignment.objects.create(
            service=self.service, center=self.other_center
        )
        CenterServiceAssignment.objects.create(
            service=self.service, center=self.inactive_center, is_active=False
        )

        self.profile = create_customer_profile("owner@example.com")
        self.therapy_program = create_therapy_program(
            self.profile,
            self.home_center,
            self.service,
            [self.redeemable_center, self.inactive_center],
        )
        self.other_profile = create_customer_profile("intruder@example.com")
        self.other_therapy_program = create_therapy_program(
            self.other_profile,
            self.home_center,
            self.service,
            [self.redeemable_center],
        )

    def test_customer_cannot_read_another_customers_profile(self):
        intruder = self.other_profile.customer.user

        foreign_profile = get_therapy_program_services(
            intruder, self.profile.pk, self.therapy_program.pk
        )
        foreign_program = get_therapy_program_services(
            intruder, self.other_profile.pk, self.therapy_program.pk
        )

        self.assertEqual(foreign_profile.status_code, 404)
        self.assertEqual(foreign_program.status_code, 404)

    def test_service_centers_are_limited_to_active_redeemable_centers(self):
        response = get_therapy_program_services(
            self.profile.customer.user, self.profile.pk, self.therapy_program.pk
        )

        self.assertEqual(response.status_code, 200)
        results = response.data["data"]
        self.assertEqual(len(results), 1)
        center_ids = [center["id"] for center in results[0]["service"]["centers"]]
        self.assertEqual(center_ids, [str(self.redeemable_center.pk)])

    def test_query_count_does_not_grow_with_services(self):
        user = self.profile.customer.user
        baseline = count_queries(user, self.profile.pk, self.therapy_program.pk)

        for index in range(3):
            service = Service.objects.create(
                name=f"Extra {index}", service_category=ServiceCategory.THERAPY
            )
            CenterServiceAssignment.objects.create(
                service=service, center=self.redeemable_center
            )
            add_therapy_service(self.therapy_program.program, service)

        self.assertEqual(
            count_queries(user, self.profile.pk, self.therapy_program.pk), baseline
        )
