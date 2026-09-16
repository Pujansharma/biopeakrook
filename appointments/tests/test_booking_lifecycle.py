from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
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
from appointments.models import (
    AssociateLeave,
    AssociateRosterEntry,
    CareTeamAvailabilityBlock,
)
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
    apply_availability_exception_hooks,
    detect_exceptions_for_appointment,
    detect_exceptions_for_source,
)
from appointments.utils.scheduling import (
    EQUIPMENT_NOT_ALLOWED_EMPTY_ROOM_MESSAGE,
    EQUIPMENT_NOT_ALLOWED_VIRTUAL_MESSAGE,
    EQUIPMENT_REQUIRED_FOR_ROOM_MESSAGE,
    HEALTH_COACH_ID_REJECT_MESSAGE,
    MISSING_DOCTOR_ROLE_MESSAGE,
    MISSING_SPECIALTY_ROLE_MESSAGE,
    ROOM_REQUIRED_IN_PERSON_MESSAGE,
    find_appointment_slots,
    resolve_booking_combo,
)
from appointments.utils.transitions import validate_transition
from appointments.views.booking import AppointmentBookView
from core.utils.constants import AppointmentModes
from inventory.models import Equipment, EquipmentType, Room, RoomType
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


def assert_slot_has_no_pin_keys(test_case, slot):
    pin_keys = (
        "associates",
        "room_id",
        "equipment_id",
        "doctor_id",
        "specialty_id",
        "care_team_id",
    )
    for pin_key in pin_keys:
        test_case.assertNotIn(pin_key, slot)


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
        payload = {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        payload.update(preferred or self.virtual_preferred)
        return payload


class BookingHappyPathTests(BookingWorldTests):
    def test_find_slots_echoes_nested_specialty(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        assert_slot_has_no_pin_keys(self, slot)
        self.assertEqual(slot["specialty"]["id"], str(self.coach.pk))
        self.assertEqual(slot["specialty"]["role"]["id"], str(self.coach_role.pk))
        self.assertEqual(slot["specialty"]["role"]["name"], self.coach_role.name)
        self.assertNotIn("doctor", slot)
        self.assertNotIn("care_team", slot)
        self.assertNotIn("room", slot)
        self.assertNotIn("equipment", slot)

    def test_find_slots_echoes_nested_doctor_and_specialty(self):
        preferred = {
            "doctor_id": str(self.doctor.pk),
            "specialty_id": str(self.coach.pk),
        }
        slots_payload = find_slots(self.center, self.virtual_slot_payload(preferred))
        slot = first_slot(slots_payload)
        assert_slot_has_no_pin_keys(self, slot)
        self.assertEqual(slot["doctor"]["id"], str(self.doctor.pk))
        self.assertNotIn("role", slot["doctor"])
        self.assertEqual(slot["specialty"]["id"], str(self.coach.pk))
        self.assertEqual(slot["specialty"]["role"]["id"], str(self.coach_role.pk))
        self.assertNotIn("care_team", slot)

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
                **self.in_person_preferred,
            },
        )
        self.assertEqual(appointment.room.pk, self.room.pk)
        self.assertIsNone(appointment.equipment)

    def test_find_slots_echoes_nested_room_without_equipment(self):
        payload = {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.IN_PERSON,
            "date": SLOT_DATE.isoformat(),
            "preferred": self.in_person_preferred,
        }
        slots_payload = find_slots(self.center, payload)
        slot = first_slot(slots_payload)
        assert_slot_has_no_pin_keys(self, slot)
        self.assertEqual(slot["room"]["id"], str(self.room.pk))
        self.assertEqual(slot["room"]["name"], self.room.name)
        self.assertNotIn("equipment", slot)
        self.assertEqual(slot["specialty"]["id"], str(self.coach.pk))

    def test_book_from_slot_staff_ids(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
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

    def test_find_slots_echoes_nested_care_team(self):
        serializer = CenterCareTeamSerializer(
            data={
                "name": "Slot Team",
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
        assert_slot_has_no_pin_keys(self, slot)
        self.assertEqual(slot["care_team"]["id"], str(care_team.pk))
        self.assertEqual(slot["care_team"]["name"], "Slot Team")
        self.assertNotIn("doctor", slot)
        self.assertNotIn("specialty", slot)


class BookingValidationTests(BookingWorldTests):
    def test_find_slots_rejects_past_date(self):
        past_date = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                {
                    **self.virtual_slot_payload(),
                    "date": past_date.isoformat(),
                },
            )
        self.assertIn("Date cannot be in the past.", drf_error_text(raised.exception))

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
        with self.assertRaises(DRFValidationError) as raised:
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
        self.assertIn("room_id", raised.exception.detail["preferred"])
        self.assertIn(
            ROOM_REQUIRED_IN_PERSON_MESSAGE,
            drf_error_text(raised.exception),
        )

    def test_book_in_person_without_room_errors_on_room_id(self):
        start = datetime(2026, 9, 21, 10, 0, tzinfo=KOLKATA)
        serializer = AppointmentBookSerializer(
            data={
                "customer_profile_id": str(self.customer_profile.pk),
                "service_id": str(self.service.pk),
                "modality": AppointmentModes.IN_PERSON,
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=30)).isoformat(),
                "specialty_id": str(self.coach.pk),
            },
            context={"center": self.center},
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn("room_id", raised.exception.detail)
        self.assertNotIn("non_field_errors", raised.exception.detail)
        self.assertIn(
            ROOM_REQUIRED_IN_PERSON_MESSAGE,
            drf_error_text(raised.exception),
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

    def test_rejects_virtual_with_equipment(self):
        with self.assertRaises(DRFValidationError) as raised:
            find_slots(
                self.center,
                self.virtual_slot_payload(
                    {
                        "specialty_id": str(self.coach.pk),
                        "equipment_id": "11111111-1111-1111-1111-111111111111",
                    }
                ),
            )
        self.assertIn(
            EQUIPMENT_NOT_ALLOWED_VIRTUAL_MESSAGE,
            drf_error_text(raised.exception),
        )

    def test_in_person_room_with_equipment_requires_equipment_id(self):
        equipment_type = EquipmentType.objects.create(
            center=self.center, name="Consult Device", is_active=True
        )
        equipment = Equipment.objects.create(
            center=self.center,
            room=self.room,
            equipment_type=equipment_type,
            name="Consult EQ 1",
            code="BK-LIFE-EQ-1",
            serial_number="SN-LIFE-1",
            is_active=True,
        )
        payload = {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.IN_PERSON,
            "date": SLOT_DATE.isoformat(),
            "preferred": self.in_person_preferred,
        }
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots(self.center, payload)
        self.assertIn(
            EQUIPMENT_REQUIRED_FOR_ROOM_MESSAGE, raised.exception.messages
        )
        payload["preferred"] = {
            **self.in_person_preferred,
            "equipment_id": str(equipment.pk),
        }
        slots_payload = find_slots(self.center, payload)
        slot = first_slot(slots_payload)
        self.assertEqual(slot["equipment"]["id"], str(equipment.pk))
        self.assertEqual(slot["equipment"]["name"], equipment.name)
        self.assertEqual(slot["room"]["id"], str(self.room.pk))
        assert_slot_has_no_pin_keys(self, slot)
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
                **self.in_person_preferred,
                "equipment_id": str(equipment.pk),
            },
        )
        self.assertEqual(appointment.equipment.pk, equipment.pk)

    def test_second_equipment_on_room_is_bookable(self):
        equipment_type = EquipmentType.objects.create(
            center=self.center, name="Consult Device", is_active=True
        )
        Equipment.objects.create(
            center=self.center,
            room=self.room,
            equipment_type=equipment_type,
            name="Consult EQ First",
            code="BK-LIFE-EQ-A",
            serial_number="SN-LIFE-A",
            is_active=True,
        )
        second = Equipment.objects.create(
            center=self.center,
            room=self.room,
            equipment_type=equipment_type,
            name="Consult EQ Second",
            code="BK-LIFE-EQ-B",
            serial_number="SN-LIFE-B",
            is_active=True,
        )
        payload = {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.IN_PERSON,
            "date": SLOT_DATE.isoformat(),
            "preferred": {
                **self.in_person_preferred,
                "equipment_id": str(second.pk),
            },
        }
        slots_payload = find_slots(self.center, payload)
        slot = first_slot(slots_payload)
        self.assertEqual(slot["equipment"]["id"], str(second.pk))
        self.assertEqual(slot["equipment"]["name"], second.name)
        assert_slot_has_no_pin_keys(self, slot)
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
                **self.in_person_preferred,
                "equipment_id": str(second.pk),
            },
        )
        self.assertEqual(appointment.equipment.pk, second.pk)

    def test_rejects_equipment_when_room_has_none(self):
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": str(self.service.pk),
                    "modality": AppointmentModes.IN_PERSON,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": {
                        **self.in_person_preferred,
                        "equipment_id": "11111111-1111-1111-1111-111111111111",
                    },
                },
            )
        self.assertIn(
            EQUIPMENT_NOT_ALLOWED_EMPTY_ROOM_MESSAGE,
            raised.exception.messages,
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

    def test_dual_specialty_hats_stamp_mapped_service_role(self):
        preferred = {"specialty_id": str(self.dual_specialty.pk)}
        slots_payload = find_slots(
            self.center, self.virtual_slot_payload(preferred)
        )
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot, preferred)
        )
        link = appointment.associate_links.get()
        self.assertEqual(link.associate.pk, self.dual_specialty.pk)
        self.assertEqual(link.role.pk, self.coach_role.pk)

    def test_specialty_without_service_role_requirement_raises(self):
        service = Service.objects.create(
            name="No Role Requirement Service",
            service_category=ServiceCategory.CONSULTATION,
        )
        CenterServiceAssignment.objects.create(
            center=self.center,
            service=service,
            duration=30,
            buffer_before=0,
            buffer_after=0,
            modality=AppointmentModes.VIRTUAL,
            is_active=True,
        )
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots(
                self.center,
                {
                    "customer_profile_id": str(self.customer_profile.pk),
                    "service_id": str(service.pk),
                    "modality": AppointmentModes.VIRTUAL,
                    "date": SLOT_DATE.isoformat(),
                    "preferred": {"specialty_id": str(self.coach.pk)},
                },
            )
        self.assertIn(MISSING_SPECIALTY_ROLE_MESSAGE, raised.exception.messages)

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
                **self.virtual_preferred,
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
                    **self.virtual_preferred,
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

    def test_moving_leave_window_resolves_stale_exception(self):
        appointment = self.book_confirmed()
        leave = AssociateLeave.objects.create(
            associate=self.coach,
            scope=LeaveScope.CENTER,
            center=self.center,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Sick",
            is_active=True,
        )
        detect_exceptions_for_source(
            ExceptionSourceType.ASSOCIATE_LEAVE,
            leave.pk,
            sync=True,
            center=self.center,
        )
        exception = appointment.exceptions.get()
        self.assertEqual(exception.status, ExceptionStatus.OPEN)
        new_start = appointment.exclusive_end_datetime + timedelta(hours=2)
        new_end = new_start + timedelta(hours=1)
        leave.start_datetime = new_start
        leave.end_datetime = new_end
        leave.save(update_fields=["start_datetime", "end_datetime", "updated_at"])
        apply_availability_exception_hooks(
            center=self.center,
            instance=leave,
            source_type=ExceptionSourceType.ASSOCIATE_LEAVE,
            validated_data={"start_datetime": new_start, "end_datetime": new_end},
            created=False,
        )
        exception.refresh_from_db()
        appointment.refresh_from_db()
        self.assertEqual(exception.status, ExceptionStatus.RESOLVED)
        self.assertEqual(exception.resolution, ExceptionResolution.BLOCKER_CLEARED)
        self.assertFalse(appointment.has_open_exception)

    def test_deactivating_care_team_resolves_block_exceptions(self):
        serializer = CenterCareTeamSerializer(
            data={
                "name": "Exception Team",
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
        block = CareTeamAvailabilityBlock.objects.create(
            center=self.center,
            care_team=care_team,
            is_recurring=False,
            start_datetime=appointment.exclusive_start_datetime,
            end_datetime=appointment.exclusive_end_datetime,
            reason="Team offsite",
            is_active=True,
        )
        detect_exceptions_for_source(
            ExceptionSourceType.CARE_TEAM_BLOCK,
            block.pk,
            sync=True,
            center=self.center,
        )
        exception = appointment.exceptions.get()
        self.assertEqual(exception.status, ExceptionStatus.OPEN)
        updater = CenterCareTeamSerializer(
            care_team,
            data={"is_active": False},
            partial=True,
            context={"center": self.center},
        )
        updater.is_valid(raise_exception=True)
        updater.save()
        exception.refresh_from_db()
        appointment.refresh_from_db()
        block.refresh_from_db()
        self.assertFalse(block.is_active)
        self.assertEqual(exception.status, ExceptionStatus.RESOLVED)
        self.assertEqual(exception.resolution, ExceptionResolution.BLOCKER_CLEARED)
        self.assertFalse(appointment.has_open_exception)


class PastDirectBookingTests(BookingWorldTests):
    def historical_payload(self):
        start = datetime(2026, 9, 14, 10, 0, tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        return {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "specialty_id": str(self.coach.pk),
        }

    def test_book_rejects_historical_start(self):
        serializer = AppointmentBookSerializer(
            data=self.historical_payload(),
            context={"center": self.center},
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn("Date cannot be in the past.", drf_error_text(raised.exception))

    def test_reschedule_rejects_historical_start(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(slot)
        )
        serializer = AppointmentRescheduleSerializer(
            appointment,
            data=self.historical_payload(),
            context={"center": self.center, "appointment": appointment},
        )
        with self.assertRaises(DRFValidationError) as raised:
            serializer.is_valid(raise_exception=True)
        self.assertIn("Date cannot be in the past.", drf_error_text(raised.exception))


class IdempotentReplayTests(BookingWorldTests):
    def setUp(self):
        super().setUp()
        UserAccount.objects.create(
            user=self.actor,
            account_type=UserType.ASSOCIATE,
        )

    def post_book(self, payload, idempotency_key):
        factory = APIRequestFactory()
        request = factory.post(
            f"/centers/{self.center.pk}/appointments/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        force_authenticate(request, user=self.actor)
        view = AppointmentBookView.as_view()
        return view(request, center_id=self.center.pk)

    def test_replay_same_key_and_payload_returns_existing_appointment(self):
        slots_payload = find_slots(self.center, self.virtual_slot_payload())
        slot = first_slot(slots_payload)
        payload = self.book_virtual_payload(slot)
        idempotency_key = str(uuid4())
        first_response = self.post_book(payload, idempotency_key)
        self.assertEqual(first_response.status_code, 201)
        replay_response = self.post_book(payload, idempotency_key)
        self.assertEqual(replay_response.status_code, 200)
        self.assertEqual(replay_response.data["detail"], "Appointment retrieved.")
        self.assertEqual(
            replay_response.data["data"]["id"],
            first_response.data["data"]["id"],
        )
