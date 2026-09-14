from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
from accounts.centers.models import Center, CenterOperatingHour
from accounts.customers.models import Customer, CustomerCenterAssignment, CustomerProfile
from accounts.users.models import User
from appointments.models import AssociateLeave, AssociateRosterEntry
from appointments.serializers.booking import (
    AppointmentBookSerializer,
    AppointmentCancelSerializer,
    AppointmentDetailSerializer,
    AppointmentLifecycleSerializer,
    AppointmentMarkLateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentSlotFindSerializer,
)
from appointments.serializers.care_teams import CenterCareTeamSerializer
from appointments.utils.constants import (
    AppointmentStatus,
    ExceptionResolution,
    ExceptionSourceType,
    ExceptionStatus,
    LeaveScope,
)
from appointments.utils.exceptions import (
    acknowledge_exception,
    detect_exceptions_for_appointment,
)
from appointments.utils.scheduling import (
    AMBIGUOUS_SPECIALTY_ROLE_MESSAGE,
    HEALTH_COACH_ID_REJECT_MESSAGE,
    MISSING_DOCTOR_ROLE_MESSAGE,
    find_appointment_slots,
    resolve_booking_combo,
)
from appointments.utils.transitions import validate_transition
from appointments.views.booking import (
    build_associate_payload,
    resolve_equipment,
    resolve_room,
)
from core.utils.constants import AppointmentModes
from inventory.models import Room, RoomType
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoleRequirement,
    CenterServiceRoomTypeRequirement,
    Service,
)
from programs.services.utils.constants import ServiceCategory

KOLKATA = ZoneInfo("Asia/Kolkata")
SLOT_DATE = date(2026, 9, 21)
WEEKDAYS = ("0", "1", "2", "3", "4", "5")
ILLEGAL_LIFECYCLE = (
    (AppointmentStatus.CONFIRMED, "start"),
    (AppointmentStatus.CONFIRMED, "complete"),
    (AppointmentStatus.CONFIRMED, "mark-late"),
    (AppointmentStatus.CHECKED_IN, "complete"),
    (AppointmentStatus.CHECKED_IN, "no-show"),
    (AppointmentStatus.CHECKED_IN, "mark-late"),
    (AppointmentStatus.IN_PROGRESS, "check-in"),
    (AppointmentStatus.IN_PROGRESS, "cancel"),
    (AppointmentStatus.IN_PROGRESS, "reschedule"),
    (AppointmentStatus.IN_PROGRESS, "no-show"),
    (AppointmentStatus.COMPLETED, "check-in"),
    (AppointmentStatus.COMPLETED, "cancel"),
    (AppointmentStatus.COMPLETED, "reschedule"),
    (AppointmentStatus.CANCELLED, "check-in"),
    (AppointmentStatus.NO_SHOW, "check-in"),
    (AppointmentStatus.NO_SHOW, "cancel"),
)


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
    CenterOperatingHour.objects.create(
        center=center,
        day_of_week="6",
        is_open=False,
        open_time=None,
        close_time=None,
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
    return profile


def first_slot(slots_payload):
    slots = slots_payload["slots"]
    if not slots:
        raise AssertionError("expected at least one slot")
    return slots[0]


def parse_slot_datetimes(slot):
    return datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])


def find_slots(center, payload):
    serializer = AppointmentSlotFindSerializer(
        data=payload,
        context={"center": center},
    )
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    return find_appointment_slots(
        center=center,
        customer_profile=validated["customer_profile"],
        service=validated["service"],
        modality=validated["modality"],
        slot_date=validated["date"],
        preferred=validated.get("preferred"),
    )


def book_appointment(center, actor, payload):
    serializer = AppointmentBookSerializer(
        data=payload,
        context={"center": center},
    )
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    combo = resolve_booking_combo(
        center=center,
        assignment=validated["assignment"],
        modality=validated["modality"],
        preferred=validated.get("preferred"),
        start=validated["start"],
        end=validated["end"],
        associates=build_associate_payload(validated.get("associates") or []),
        room=resolve_room(center, validated.get("room_id")),
        equipment=resolve_equipment(center, validated.get("equipment_id")),
        customer_profile=validated["customer_profile"],
    )
    serializer.save(
        assignment=validated["assignment"],
        room=combo["room"],
        equipment=combo["equipment"],
        associates_payload=combo["associates"],
        care_team=combo["care_team"],
        actor=actor,
    )
    return serializer.instance


def run_lifecycle(appointment, action, actor):
    serializer = AppointmentLifecycleSerializer(
        appointment,
        data={},
        context={"appointment": appointment, "action": action},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(actor=actor)
    return serializer.instance


def cancel_appointment(appointment, actor, reason="Patient cancelled"):
    serializer = AppointmentCancelSerializer(
        appointment,
        data={"reason": reason},
        context={"appointment": appointment},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(actor=actor)
    return serializer.instance


def mark_late(appointment, actor, late_by=10):
    serializer = AppointmentMarkLateSerializer(
        appointment,
        data={"late_by": late_by},
        context={"appointment": appointment},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(actor=actor)
    return serializer.instance


def reschedule_appointment(center, appointment, actor, payload):
    serializer = AppointmentRescheduleSerializer(
        appointment,
        data=payload,
        context={"center": center, "appointment": appointment},
    )
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    combo = resolve_booking_combo(
        center=center,
        assignment=validated["assignment"],
        modality=validated["modality"],
        preferred=validated.get("preferred"),
        start=validated["start"],
        end=validated["end"],
        associates=build_associate_payload(validated.get("associates") or []),
        room=resolve_room(center, validated.get("room_id")),
        equipment=resolve_equipment(center, validated.get("equipment_id")),
        customer_profile=validated["customer_profile"],
        exclude_appointment=appointment,
    )
    serializer.save(
        assignment=validated["assignment"],
        room=combo["room"],
        equipment=combo["equipment"],
        associates_payload=combo["associates"],
        care_team=combo["care_team"],
        actor=actor,
    )
    return serializer.instance


def drf_error_text(error):
    return str(error.detail)


class BookingWorldTests(TestCase):
    def setUp(self):
        self.center = Center.objects.create(
            name="Booking World",
            code="BK-LIFE",
            modes=AppointmentModes.BOTH,
        )
        seed_weekday_hours(self.center)
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.nutrition_role = create_role(self.center, "Nutritionist")
        self.doctor = create_assigned_associate(
            self.center, "life-doctor@example.com", self.doctor_role
        )
        self.coach = create_assigned_associate(
            self.center, "life-coach@example.com", self.coach_role
        )
        self.dual_specialty = create_assigned_associate(
            self.center,
            "life-dual@example.com",
            self.coach_role,
            self.nutrition_role,
        )
        self.actor = self.doctor.user
        self.customer_profile = create_customer_profile(
            self.center, "life-patient@example.com"
        )
        self.service = Service.objects.create(
            name="Lifecycle Consult QA",
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
            name="Consult 1",
            code="BK-LIFE-RM-1",
            room_type_ref=self.room_type,
            is_active=True,
        )
        self.virtual_preferred = {"specialty_id": str(self.coach.pk)}
        self.in_person_preferred = {
            "specialty_id": str(self.coach.pk),
            "room_id": str(self.room.pk),
        }

    def virtual_slot_payload(self, preferred=None):
        return {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "date": SLOT_DATE.isoformat(),
            "preferred": preferred or self.virtual_preferred,
        }

    def book_virtual_payload(self, slot, preferred=None):
        start, end = parse_slot_datetimes(slot)
        return {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "preferred": preferred or self.virtual_preferred,
        }


class BookingHappyPathTests(BookingWorldTests):
    def test_find_slots_and_book_virtual_specialty(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
        )
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)
        self.assertEqual(appointment.modality, AppointmentModes.VIRTUAL)
        link = appointment.associate_links.get()
        self.assertEqual(link.associate.pk, self.coach.pk)
        self.assertEqual(link.role.pk, self.coach_role.pk)

    def test_book_doctor_plus_specialty_stamps_both_hats(self):
        preferred = {
            "doctor_id": str(self.doctor.pk),
            "specialty_id": str(self.coach.pk),
        }
        slots_payload = find_slots(self.center, self.virtual_slot_payload(preferred))
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center,
            self.actor,
            self.book_virtual_payload(slot, preferred),
        )
        role_ids = set(
            appointment.associate_links.values_list("role_id", flat=True)
        )
        self.assertEqual(role_ids, {self.doctor_role.pk, self.coach_role.pk})

    def test_book_in_person_with_preferred_room(self):
        payload = {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.IN_PERSON,
            "date": SLOT_DATE.isoformat(),
            "preferred": self.in_person_preferred,
        }
        slots_payload = find_slots(self.center, payload)
        slot = first_slot(slots_payload)
        start, end = parse_slot_datetimes(slot)
        appointment = book_appointment(
            self.center,
            self.actor,
            {
                "customer_profile_id": str(self.customer_profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.IN_PERSON,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "preferred": self.in_person_preferred,
            },
        )
        self.assertEqual(appointment.room.pk, self.room.pk)
        self.assertIsNone(appointment.equipment)

    def test_book_from_slot_pin(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        start, end = parse_slot_datetimes(slot)
        appointment = book_appointment(
            self.center,
            self.actor,
            {
                "customer_profile_id": str(self.customer_profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.VIRTUAL,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "associates": slot["associates"],
            },
        )
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)

    def test_book_care_team_preferred(self):
        serializer = CenterCareTeamSerializer(
            data={
                "name": "Lifecycle Team",
                "members": [
                    {
                        "associate_id": self.doctor.pk,
                        "role_id": self.doctor_role.pk,
                    },
                    {
                        "associate_id": self.coach.pk,
                        "role_id": self.coach_role.pk,
                    },
                ],
            },
            context={"center": self.center},
        )
        serializer.is_valid(raise_exception=True)
        care_team = serializer.save(center=self.center)
        preferred = {"care_team_id": str(care_team.pk)}
        slots_payload = find_slots(self.center, self.virtual_slot_payload(preferred))
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center,
            self.actor,
            self.book_virtual_payload(slot, preferred),
        )
        self.assertEqual(appointment.care_team.pk, care_team.pk)
        self.assertEqual(appointment.associate_links.count(), 2)


class BookingValidationTests(BookingWorldTests):
    def test_find_slots_requires_preferred(self):
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.VIRTUAL,
                    "date": SLOT_DATE.isoformat(),
                },
            )
        self.assertIn("required", drf_error_text(raised.exception).lower())

    def test_rejects_health_coach_id(self):
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {"health_coach_id": str(self.coach.pk)}
                ),
            )
        self.assertIn(HEALTH_COACH_ID_REJECT_MESSAGE, drf_error_text(raised.exception))

    def test_rejects_same_person_as_doctor_and_specialty(self):
        with self.assertRaises(DRFValidationError):
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {
                        "doctor_id": str(self.coach.pk),
                        "specialty_id": str(self.coach.pk),
                    }
                ),
            )

    def test_rejects_care_team_with_specialty(self):
        with self.assertRaises(DRFValidationError):
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {
                        "care_team_id": "11111111-1111-1111-1111-111111111111",
                        "specialty_id": str(self.coach.pk),
                    }
                ),
            )

    def test_rejects_in_person_without_room(self):
        with self.assertRaises(DRFValidationError):
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.IN_PERSON,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": {"specialty_id": str(self.coach.pk)},
                },
            )

    def test_rejects_virtual_with_room(self):
        with self.assertRaises(DRFValidationError):
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {
                        "specialty_id": str(self.coach.pk),
                        "room_id": str(self.room.pk),
                    }
                ),
            )

    def test_rejects_both_modality(self):
        with self.assertRaises(DRFValidationError):
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.BOTH,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": self.virtual_preferred,
                },
            )

    def test_rejects_invalid_customer(self):
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                {
                    "customer_profile_id": "11111111-1111-1111-1111-111111111111",
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.VIRTUAL,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": self.virtual_preferred,
                },
            )
        self.assertIn("Invalid customer profile", drf_error_text(raised.exception))

    def test_rejects_invalid_service(self):
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": "11111111-1111-1111-1111-111111111111",
                    "modality": AppointmentModes.VIRTUAL,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": self.virtual_preferred,
                },
            )
        self.assertIn("Invalid service", drf_error_text(raised.exception))

    def test_doctor_without_doctor_hat_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots(
                self.center,
                self.virtual_slot_payload({"doctor_id": str(self.coach.pk)}),
            )
        self.assertIn(MISSING_DOCTOR_ROLE_MESSAGE, raised.exception.messages)

    def test_ambiguous_specialty_hats_raise(self):
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {"specialty_id": str(self.dual_specialty.pk)}
                ),
            )
        self.assertIn(AMBIGUOUS_SPECIALTY_ROLE_MESSAGE, raised.exception.messages)

    def test_second_book_same_slot_blocked(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
        )
        with self.assertRaises(DjangoValidationError):
            book_appointment(
                self.center, self.actor, self.book_virtual_payload(slot)
            )


class LifecycleTests(BookingWorldTests):
    def book_confirmed(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        return book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
        )

    def test_check_in_start_complete(self):
        appointment = self.book_confirmed()
        appointment = run_lifecycle(appointment, "check-in", self.actor)
        self.assertEqual(appointment.status, AppointmentStatus.CHECKED_IN)
        appointment = run_lifecycle(appointment, "start", self.actor)
        self.assertEqual(appointment.status, AppointmentStatus.IN_PROGRESS)
        appointment = run_lifecycle(appointment, "complete", self.actor)
        self.assertEqual(appointment.status, AppointmentStatus.COMPLETED)

    def test_mark_late_from_in_progress(self):
        appointment = self.book_confirmed()
        appointment = run_lifecycle(appointment, "check-in", self.actor)
        appointment = run_lifecycle(appointment, "start", self.actor)
        appointment = mark_late(appointment, self.actor, late_by=12)
        self.assertEqual(appointment.status, AppointmentStatus.IN_PROGRESS)
        self.assertTrue(appointment.is_late)
        self.assertEqual(appointment.late_by, 12)

    def test_cancel_from_confirmed_and_checked_in(self):
        confirmed = self.book_confirmed()
        confirmed = cancel_appointment(confirmed, self.actor)
        self.assertEqual(confirmed.status, AppointmentStatus.CANCELLED)
        self.assertEqual(confirmed.cancel_reason, "Patient cancelled")

        second = self.book_confirmed()
        second = run_lifecycle(second, "check-in", self.actor)
        second = cancel_appointment(second, self.actor, reason="No longer needed")
        self.assertEqual(second.status, AppointmentStatus.CANCELLED)

    def test_no_show_from_confirmed(self):
        appointment = self.book_confirmed()
        appointment = run_lifecycle(appointment, "no-show", self.actor)
        self.assertEqual(appointment.status, AppointmentStatus.NO_SHOW)

    def test_reschedule_from_confirmed_lands_confirmed(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        first_slot_row = slots_payload["slots"][0]
        later_slot = slots_payload["slots"][2]
        appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(first_slot_row)
        )
        original_start = appointment.start_datetime
        start, end = parse_slot_datetimes(later_slot)
        appointment = reschedule_appointment(
            self.center,
            appointment,
            self.actor,
            {
                "customer_profile_id": str(self.customer_profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.VIRTUAL,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "preferred": self.virtual_preferred,
            },
        )
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)
        self.assertNotEqual(appointment.start_datetime, original_start)

    def test_reschedule_rejects_customer_change(self):
        appointment = self.book_confirmed()
        other_profile = create_customer_profile(
            self.center, "life-other@example.com", first_name="Other", last_name="Person"
        )
        start = appointment.start_datetime + timedelta(hours=1)
        end = start + timedelta(minutes=30)
        with self.assertRaises(DRFValidationError) as raised:
            reschedule_appointment(
                self.center,
                appointment,
                self.actor,
                {
                    "customer_profile_id": str(other_profile.pk),
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.VIRTUAL,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "preferred": self.virtual_preferred,
                },
            )
        self.assertIn("Cannot change the customer", drf_error_text(raised.exception))

    def test_illegal_transitions_raise(self):
        appointment = self.book_confirmed()
        for status, action in ILLEGAL_LIFECYCLE:
            appointment.status = status
            appointment.save(update_fields=["status", "updated_at"])
            with self.assertRaises(DjangoValidationError):
                validate_transition(appointment.status, action)

    def test_unknown_action_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            validate_transition(AppointmentStatus.CONFIRMED, "explode")
        self.assertIn("Unknown appointment action", raised.exception.messages[0])


class ExceptionRaisingTests(BookingWorldTests):
    def book_confirmed(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        return book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
        )

    def test_overlapping_leave_raises_open_exception(self):
        appointment = self.book_confirmed()
        AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Sick",
            is_active=True,
        )
        created = detect_exceptions_for_appointment(appointment)
        appointment.refresh_from_db()
        self.assertGreaterEqual(created, 1)
        self.assertTrue(appointment.has_open_exception)
        exception = appointment.exceptions.get()
        self.assertEqual(exception.status, ExceptionStatus.OPEN)
        self.assertEqual(exception.source_type, ExceptionSourceType.ASSOCIATE_LEAVE)
        hint = AppointmentDetailSerializer(appointment).data[
            "exception_resolution_hint"
        ]
        self.assertIn("cancelling", hint)

    def test_acknowledge_clears_open_exception_flag(self):
        appointment = self.book_confirmed()
        AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Leave",
            is_active=True,
        )
        detect_exceptions_for_appointment(appointment)
        exception = appointment.exceptions.get()
        acknowledge_exception(exception, self.actor)
        appointment.refresh_from_db()
        exception.refresh_from_db()
        self.assertFalse(appointment.has_open_exception)
        self.assertEqual(exception.status, ExceptionStatus.RESOLVED)
        self.assertEqual(exception.resolution, ExceptionResolution.ACKNOWLEDGED)

    def test_cancel_resolves_open_exceptions(self):
        appointment = self.book_confirmed()
        AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Leave",
            is_active=True,
        )
        detect_exceptions_for_appointment(appointment)
        appointment = cancel_appointment(appointment, self.actor)
        exception = appointment.exceptions.get()
        self.assertEqual(exception.status, ExceptionStatus.RESOLVED)
        self.assertEqual(exception.resolution, ExceptionResolution.CANCELLED)
        self.assertFalse(appointment.has_open_exception)

    def test_in_progress_exception_hint_is_ack_only(self):
        appointment = self.book_confirmed()
        appointment = run_lifecycle(appointment, "check-in", self.actor)
        appointment = run_lifecycle(appointment, "start", self.actor)
        AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Leave",
            is_active=True,
        )
        detect_exceptions_for_appointment(appointment)
        appointment.refresh_from_db()
        hint = AppointmentDetailSerializer(appointment).data[
            "exception_resolution_hint"
        ]
        self.assertIn("acknowledged", hint)
        with self.assertRaises(DjangoValidationError):
            validate_transition(appointment.status, "cancel")

    def test_non_overlapping_leave_does_not_raise(self):
        appointment = self.book_confirmed()
        AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_end_datetime + timedelta(hours=2),
            end_datetime=appointment.exclusive_end_datetime + timedelta(hours=3),
            reason="Later",
            is_active=True,
        )
        created = detect_exceptions_for_appointment(appointment)
        appointment.refresh_from_db()
        self.assertEqual(created, 0)
        self.assertFalse(appointment.has_open_exception)
