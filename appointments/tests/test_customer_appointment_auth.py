from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center, CenterOperatingHour
from accounts.customers.models import Customer, CustomerCenterAssignment, CustomerProfile
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from appointments.models import Appointment, AssociateRosterEntry
from appointments.serializers.booking import (
    AppointmentBookSerializer,
    AppointmentLifecycleSerializer,
    CUSTOMER_BOOKING_DATE_MESSAGE,
    CUSTOMER_BOOKING_WINDOW_DAYS,
    CUSTOMER_PREFERRED_FORBIDDEN_MESSAGE,
    CUSTOMER_PROFILE_NOT_OWNED_MESSAGE,
    CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE,
    PROGRAM_SERVICE_MISMATCH_MESSAGE,
    STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE,
)
from appointments.utils.constants import AppointmentStatus
from appointments.utils.redemption import (
    force_complete_appointment,
    program_expiry_before_appointment_message,
)
from appointments.utils.scheduling import find_appointment_slots_v2
from appointments.views.booking import (
    AppointmentCancelView,
    AppointmentCollectionView,
    AppointmentCustomerAppointmentsListView,
    AppointmentRescheduleView,
    AppointmentSlotFindView,
)
from core.utils.constants import AppointmentModes
from inventory.models import Room, RoomType
from programs.models import Program, ProgramService, TherapyProgram, TherapyProgramService
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoleRequirement,
    CenterServiceRoomTypeRequirement,
    Service,
)
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType

KOLKATA = ZoneInfo("Asia/Kolkata")
WEEKDAYS = ("0", "1", "2", "3", "4", "5")


def next_weekday_slot_date():
    candidate = timezone.localdate() + timedelta(days=1)
    while candidate.weekday() > 5:
        candidate += timedelta(days=1)
    return candidate


SLOT_DATE = next_weekday_slot_date()


def seed_weekday_hours(center):
    for day_of_week in WEEKDAYS:
        CenterOperatingHour.objects.create(
            center=center,
            day_of_week=day_of_week,
            is_open=True,
            open_time=time(9, 0),
            close_time=time(18, 0),
            is_active=True,
        )


def seed_roster(center, associate):
    for day_of_week in WEEKDAYS:
        AssociateRosterEntry.objects.create(
            center=center,
            associate=associate,
            day_of_week=day_of_week,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_active=True,
        )


def create_role(center, name):
    return AssociateRole.objects.create(center=center, name=name, is_active=True)


def assign_roles(assignment, *roles):
    AssociateCenterAssignmentRole.objects.filter(assignment=assignment).delete()
    AssociateCenterAssignmentRole.objects.bulk_create(
        [
            AssociateCenterAssignmentRole(assignment=assignment, role=role)
            for role in roles
            if role is not None
        ]
    )


def set_account_type(user, account_type):
    account, _created = UserAccount.objects.get_or_create(user=user)
    if account.account_type != account_type:
        account.account_type = account_type
        account.save(update_fields=["account_type"])


def create_assigned_associate(center, email, *roles):
    user = User.objects.create_user(email=email)
    associate = Associate.objects.create(user=user)
    assignment = AssociateCenterAssignment.objects.create(
        associate=associate,
        center=center,
        is_active=True,
        mode=AppointmentModes.BOTH,
        is_care_staff=True,
    )
    assign_roles(assignment, *roles)
    seed_roster(center, associate)
    set_account_type(user, UserType.ASSOCIATE)
    return associate


def create_customer_profile(center, email, first_name="Pat", last_name="Ient"):
    user = User.objects.create_user(email=email)
    customer = Customer.objects.create(user=user, contact_email=email)
    profile = CustomerProfile.objects.create(
        customer=customer,
        first_name=first_name,
        last_name=last_name,
        is_main=True,
    )
    CustomerCenterAssignment.objects.create(
        customer_profile=profile,
        center=center,
        is_primary=True,
        is_active=True,
    )
    set_account_type(user, UserType.CUSTOMER)
    return profile


def create_therapy_program_service(customer_profile, center, service, sessions_count=5):
    program = Program.objects.create(
        customer_profile=customer_profile,
        center=center,
        program_type=ProgramType.THERAPY,
    )
    TherapyProgram.objects.create(program=program)
    program_service = ProgramService.objects.create(program=program, service=service)
    return TherapyProgramService.objects.create(
        program_service=program_service,
        sessions_count=sessions_count,
    )


class CustomerAppointmentAuthTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.center = Center.objects.create(
            name="Customer Auth Center",
            code="CUST-AUTH",
            modes=AppointmentModes.BOTH,
        )
        seed_weekday_hours(self.center)
        self.coach_role = create_role(self.center, "Health Coach")
        self.coach = create_assigned_associate(
            self.center, "cust-auth-coach@example.com", self.coach_role
        )
        self.staff = self.coach.user
        self.profile = create_customer_profile(
            self.center, "cust-auth-patient@example.com"
        )
        self.customer_user = self.profile.customer.user
        self.other_profile = create_customer_profile(
            self.center, "cust-auth-other@example.com", first_name="Other"
        )
        self.service = Service.objects.create(
            name="Customer Auth Consult",
            service_category=ServiceCategory.CONSULTATION,
        )
        self.assignment = CenterServiceAssignment.objects.create(
            center=self.center,
            service=self.service,
            duration=30,
            buffer_before=0,
            buffer_after=0,
            modality=AppointmentModes.BOTH,
            is_active=True,
        )
        CenterServiceRoleRequirement.objects.create(
            assignment=self.assignment,
            role=self.coach_role,
        )
        self.room_type = RoomType.objects.create(
            center=self.center, name="Consult", is_active=True
        )
        CenterServiceRoomTypeRequirement.objects.create(
            assignment=self.assignment,
            room_type=self.room_type,
        )
        self.room = Room.objects.create(
            center=self.center,
            name="Room A",
            code="CUST-AUTH-RM",
            room_type_ref=self.room_type,
            is_active=True,
        )
        self.therapy_program_service = create_therapy_program_service(
            self.profile,
            self.center,
            self.service,
        )
        self.program_service_id = self.therapy_program_service.program_service_id

    def virtual_slot_body(self, profile):
        return {
            "customer_profile_id": str(profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "date": SLOT_DATE.isoformat(),
        }

    def book_from_slot(self, actor, profile, slot, program_service_id=None):
        specialty = slot["specialty"]
        if isinstance(specialty, list):
            specialty_id = [item["id"] for item in specialty]
        else:
            specialty_id = specialty["id"]
        payload = {
            "start": slot["start"],
            "end": slot["end"],
            "customer_profile_id": str(profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "specialty_id": specialty_id,
        }
        if program_service_id is not None:
            payload["program_service_id"] = str(program_service_id)
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/",
            payload,
            format="json",
        )
        force_authenticate(request, user=actor)
        response = AppointmentCollectionView.as_view()(
            request, center_id=self.center.pk
        )
        return response

    def reschedule_payload(self, profile, slot, program_service_id=None):
        specialty = slot["specialty"]
        if isinstance(specialty, list):
            specialty_id = [item["id"] for item in specialty]
        else:
            specialty_id = specialty["id"]
        payload = {
            "start": slot["start"],
            "end": slot["end"],
            "customer_profile_id": str(profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "specialty_id": specialty_id,
        }
        if program_service_id is not None:
            payload["program_service_id"] = str(program_service_id)
        return payload

    def post_reschedule(self, actor, appointment_id, payload):
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/{appointment_id}/reschedule/",
            payload,
            format="json",
        )
        force_authenticate(request, user=actor)
        return AppointmentRescheduleView.as_view()(
            request,
            center_id=self.center.pk,
            pk=appointment_id,
        )
    def test_slots_rejects_staff_without_preferred(self):
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            self.virtual_slot_body(self.profile),
            format="json",
        )
        force_authenticate(request, user=self.staff)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)

    def test_slots_auto_assign_allows_customer_own_profile(self):
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            self.virtual_slot_body(self.profile),
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data["data"]["slots"]), 0)

    def test_slots_rejects_customer_with_preferred(self):
        body = self.virtual_slot_body(self.profile)
        body["preferred"] = {"specialty_id": str(self.coach.pk)}
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            body,
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(CUSTOMER_PREFERRED_FORBIDDEN_MESSAGE, str(response.data))

    def test_slots_rejects_customer_date_today(self):
        body = self.virtual_slot_body(self.profile)
        body["date"] = timezone.localdate().isoformat()
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            body,
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(CUSTOMER_BOOKING_DATE_MESSAGE, str(response.data))

    def test_slots_rejects_customer_date_beyond_window(self):
        body = self.virtual_slot_body(self.profile)
        body["date"] = (
            timezone.localdate()
            + timedelta(days=CUSTOMER_BOOKING_WINDOW_DAYS + 1)
        ).isoformat()
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            body,
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(CUSTOMER_BOOKING_DATE_MESSAGE, str(response.data))

    def test_book_rejects_customer_start_beyond_window(self):
        start = datetime.combine(
            timezone.localdate()
            + timedelta(days=CUSTOMER_BOOKING_WINDOW_DAYS + 1),
            time(10, 0),
            tzinfo=KOLKATA,
        )
        end = start + timedelta(minutes=30)
        serializer = AppointmentBookSerializer(
            data={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "customer_profile_id": str(self.profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.VIRTUAL,
                "specialty_id": str(self.coach.pk),
                "program_service_id": str(self.program_service_id),
            },
            context={
                "center": self.center,
                "request": SimpleNamespace(user=self.customer_user),
            },
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn(CUSTOMER_BOOKING_DATE_MESSAGE, str(raised.exception.detail))

    def test_slots_rejects_other_customer_profile(self):
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            self.virtual_slot_body(self.other_profile),
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            CUSTOMER_PROFILE_NOT_OWNED_MESSAGE,
            str(response.data),
        )

    def test_calendar_list_rejects_customer(self):
        request = self.factory.get(
            f"/centers/{self.center.pk}/appointments/?start={SLOT_DATE.isoformat()}"
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentCollectionView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_appointments_list_own_profile(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(
            self.customer_user,
            self.profile,
            slot,
            program_service_id=self.program_service_id,
        )
        self.assertEqual(book_response.status_code, 201)

        request = self.factory.get(
            f"/appointments/customer-appointments/{self.profile.pk}/"
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentCustomerAppointmentsListView.as_view()(
            request,
            customer_profile_id=self.profile.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["total_count"], 1)
        appointment = response.data["data"]["appointments"][0]
        self.assertEqual(
            appointment["center"],
            {
                "id": str(self.center.pk),
                "code": self.center.code,
                "name": self.center.name,
            },
        )

    def test_customer_appointments_list_therapy_service_program_filter(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        self.assertGreaterEqual(len(slots["slots"]), 2)
        program_book = self.book_from_slot(
            self.customer_user,
            self.profile,
            slots["slots"][0],
            program_service_id=self.program_service_id,
        )
        self.assertEqual(program_book.status_code, 201)
        walk_in_book = self.book_from_slot(
            self.staff,
            self.profile,
            slots["slots"][1],
        )
        self.assertEqual(walk_in_book.status_code, 201)
        program_id = program_book.data["data"]["id"]
        walk_in_id = walk_in_book.data["data"]["id"]

        all_request = self.factory.get(
            f"/appointments/customer-appointments/{self.profile.pk}/"
        )
        force_authenticate(all_request, user=self.customer_user)
        all_response = AppointmentCustomerAppointmentsListView.as_view()(
            all_request,
            customer_profile_id=self.profile.pk,
        )
        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(all_response.data["data"]["total_count"], 2)

        program_request = self.factory.get(
            f"/appointments/customer-appointments/{self.profile.pk}/",
            {"therapy_service_program": "1"},
        )
        force_authenticate(program_request, user=self.customer_user)
        program_response = AppointmentCustomerAppointmentsListView.as_view()(
            program_request,
            customer_profile_id=self.profile.pk,
        )
        self.assertEqual(program_response.status_code, 200)
        program_ids = [
            row["id"] for row in program_response.data["data"]["appointments"]
        ]
        self.assertEqual(program_ids, [program_id])

        walk_in_request = self.factory.get(
            f"/appointments/customer-appointments/{self.profile.pk}/",
            {"therapy_service_program": "0"},
        )
        force_authenticate(walk_in_request, user=self.customer_user)
        walk_in_response = AppointmentCustomerAppointmentsListView.as_view()(
            walk_in_request,
            customer_profile_id=self.profile.pk,
        )
        self.assertEqual(walk_in_response.status_code, 200)
        walk_in_ids = [
            row["id"] for row in walk_in_response.data["data"]["appointments"]
        ]
        self.assertEqual(walk_in_ids, [walk_in_id])

    def test_customer_appointments_list_rejects_other_profile(self):
        request = self.factory.get(
            f"/appointments/customer-appointments/{self.other_profile.pk}/"
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentCustomerAppointmentsListView.as_view()(
            request,
            customer_profile_id=self.other_profile.pk,
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_appointments_list_rejects_staff(self):
        request = self.factory.get(
            f"/appointments/customer-appointments/{self.profile.pk}/"
        )
        force_authenticate(request, user=self.staff)
        response = AppointmentCustomerAppointmentsListView.as_view()(
            request,
            customer_profile_id=self.profile.pk,
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_book_requires_program_service_id(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(self.customer_user, self.profile, slot)
        self.assertEqual(book_response.status_code, 400)
        self.assertIn(
            CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE,
            str(book_response.data),
        )

    def test_staff_book_omits_program_service_id(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(self.staff, self.profile, slot)
        self.assertEqual(book_response.status_code, 201)
        self.assertIsNone(book_response.data["data"]["program_service_id"])

    def test_staff_book_rejects_program_service_id(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(
            self.staff,
            self.profile,
            slot,
            program_service_id=self.program_service_id,
        )
        self.assertEqual(book_response.status_code, 400)
        self.assertIn(
            STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE,
            str(book_response.data),
        )

    def test_customer_can_book_and_cancel_own(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(
            self.customer_user,
            self.profile,
            slot,
            program_service_id=self.program_service_id,
        )
        self.assertEqual(book_response.status_code, 201)
        self.assertEqual(
            book_response.data["data"]["program_service_id"],
            str(self.program_service_id),
        )
        appointment_id = book_response.data["data"]["id"]

        cancel_request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/{appointment_id}/cancel/",
            {"reason": "Changed plans"},
            format="json",
        )
        force_authenticate(cancel_request, user=self.customer_user)
        cancel_response = AppointmentCancelView.as_view()(
            cancel_request,
            center_id=self.center.pk,
            pk=appointment_id,
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(
            cancel_response.data["data"]["status"],
            AppointmentStatus.CANCELLED.label,
        )

    def test_customer_cannot_cancel_other_profile_appointment(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.other_profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        slot = slots["slots"][0]
        book_response = self.book_from_slot(self.staff, self.other_profile, slot)
        self.assertEqual(book_response.status_code, 201)
        appointment_id = book_response.data["data"]["id"]

        cancel_request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/{appointment_id}/cancel/",
            {"reason": "Not mine"},
            format="json",
        )
        force_authenticate(cancel_request, user=self.customer_user)
        cancel_response = AppointmentCancelView.as_view()(
            cancel_request,
            center_id=self.center.pk,
            pk=appointment_id,
        )
        self.assertEqual(cancel_response.status_code, 404)

    def test_book_serializer_rejects_other_profile_for_customer(self):
        start = datetime.combine(SLOT_DATE, time(10, 0), tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        serializer = AppointmentBookSerializer(
            data={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "customer_profile_id": str(self.other_profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.VIRTUAL,
                "specialty_id": str(self.coach.pk),
            },
            context={
                "center": self.center,
                "request": SimpleNamespace(user=self.customer_user),
            },
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn(CUSTOMER_PROFILE_NOT_OWNED_MESSAGE, str(raised.exception.detail))

    def test_customer_reschedule_requires_matching_program_service_id(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        book_response = self.book_from_slot(
            self.customer_user,
            self.profile,
            slots["slots"][0],
            program_service_id=self.program_service_id,
        )
        self.assertEqual(book_response.status_code, 201)
        appointment_id = book_response.data["data"]["id"]

        later_slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        self.assertGreaterEqual(len(later_slots["slots"]), 1)
        new_slot = later_slots["slots"][0]

        missing = self.post_reschedule(
            self.customer_user,
            appointment_id,
            self.reschedule_payload(self.profile, new_slot),
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn(CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE, str(missing.data))

        other_program = create_therapy_program_service(
            self.profile,
            self.center,
            self.service,
        )
        mismatched = self.post_reschedule(
            self.customer_user,
            appointment_id,
            self.reschedule_payload(
                self.profile,
                new_slot,
                program_service_id=other_program.program_service_id,
            ),
        )
        self.assertEqual(mismatched.status_code, 400)
        self.assertIn(PROGRAM_SERVICE_MISMATCH_MESSAGE, str(mismatched.data))

        ok = self.post_reschedule(
            self.customer_user,
            appointment_id,
            self.reschedule_payload(
                self.profile,
                new_slot,
                program_service_id=self.program_service_id,
            ),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(
            ok.data["data"]["program_service_id"],
            str(self.program_service_id),
        )
        self.assertEqual(ok.data["data"]["status"], AppointmentStatus.CONFIRMED.label)

    def test_staff_reschedule_rejects_program_service_id(self):
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        book_response = self.book_from_slot(self.staff, self.profile, slots["slots"][0])
        self.assertEqual(book_response.status_code, 201)
        appointment_id = book_response.data["data"]["id"]

        later_slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        new_slot = later_slots["slots"][0]
        response = self.post_reschedule(
            self.staff,
            appointment_id,
            self.reschedule_payload(
                self.profile,
                new_slot,
                program_service_id=self.program_service_id,
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE, str(response.data))

    def _set_program_expires_at(self, expires_at):
        program = self.therapy_program_service.program_service.program
        program.expires_at = expires_at
        program.save(update_fields=["expires_at"])
        return program

    def _book_therapy_slot(self, slot_date=None):
        target_date = slot_date if slot_date is not None else SLOT_DATE
        slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            target_date,
        )
        self.assertGreater(len(slots["slots"]), 0)
        book_response = self.book_from_slot(
            self.customer_user,
            self.profile,
            slots["slots"][0],
            program_service_id=self.program_service_id,
        )
        self.assertEqual(book_response.status_code, 201)
        return Appointment.objects.get(pk=book_response.data["data"]["id"])

    def test_slots_reject_date_after_program_expiry(self):
        expires_at = timezone.localdate()
        self._set_program_expires_at(expires_at)
        body = self.virtual_slot_body(self.profile)
        body["date"] = SLOT_DATE.isoformat()
        request = self.factory.post(
            f"/centers/{self.center.pk}/appointments/slots/",
            body,
            format="json",
        )
        force_authenticate(request, user=self.customer_user)
        response = AppointmentSlotFindView.as_view()(
            request, center_id=self.center.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            program_expiry_before_appointment_message(expires_at),
            str(response.data),
        )

    def test_book_rejects_start_after_program_expiry(self):
        expires_at = timezone.localdate()
        self._set_program_expires_at(expires_at)
        start = datetime.combine(SLOT_DATE, time(10, 0), tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        serializer = AppointmentBookSerializer(
            data={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "customer_profile_id": str(self.profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.VIRTUAL,
                "specialty_id": str(self.coach.pk),
                "program_service_id": str(self.program_service_id),
            },
            context={
                "center": self.center,
                "request": SimpleNamespace(user=self.customer_user),
            },
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn(
            program_expiry_before_appointment_message(expires_at),
            str(raised.exception.detail),
        )

    def test_book_allows_start_on_program_expiry_date(self):
        self._set_program_expires_at(SLOT_DATE)
        appointment = self._book_therapy_slot(SLOT_DATE)
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)

    def test_reschedule_rejects_start_after_program_expiry(self):
        appointment = self._book_therapy_slot(SLOT_DATE)
        expires_at = timezone.localdate()
        self._set_program_expires_at(expires_at)
        later_slots = find_appointment_slots_v2(
            self.center,
            self.profile,
            self.service,
            AppointmentModes.VIRTUAL,
            SLOT_DATE,
        )
        new_slot = later_slots["slots"][-1]
        response = self.post_reschedule(
            self.customer_user,
            appointment.pk,
            self.reschedule_payload(
                self.profile,
                new_slot,
                program_service_id=self.program_service_id,
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            program_expiry_before_appointment_message(expires_at),
            str(response.data),
        )

    def test_complete_rejects_when_start_after_program_expiry(self):
        appointment = self._book_therapy_slot(SLOT_DATE)
        expires_at = SLOT_DATE - timedelta(days=1)
        self._set_program_expires_at(expires_at)
        appointment.status = AppointmentStatus.IN_PROGRESS
        appointment.save(update_fields=["status", "updated_at"])
        serializer = AppointmentLifecycleSerializer(
            appointment,
            data={},
            context={"appointment": appointment, "action": "complete"},
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn(
            program_expiry_before_appointment_message(expires_at),
            str(raised.exception.detail),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, AppointmentStatus.IN_PROGRESS)

    def test_force_complete_rejects_when_start_after_program_expiry(self):
        appointment = self._book_therapy_slot(SLOT_DATE)
        expires_at = SLOT_DATE - timedelta(days=1)
        self._set_program_expires_at(expires_at)
        with self.assertRaises(DRFValidationError) as raised:
            force_complete_appointment(appointment, self.staff)
        self.assertIn(
            program_expiry_before_appointment_message(expires_at),
            str(raised.exception.detail),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)
