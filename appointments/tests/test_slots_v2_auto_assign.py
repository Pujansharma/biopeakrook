from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.utils import timezone
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
from appointments.models import AssociateRosterEntry
from appointments.serializers.booking import (
    AppointmentBookSerializer,
    AppointmentSlotFindSerializer,
)
from appointments.utils.constants import AppointmentStatus
from appointments.utils.scheduling import (
    AUTO_ASSIGN_NO_ROLE_REQUIREMENTS_MESSAGE,
    AUTO_ASSIGN_NO_ROOM_TYPE_REQUIREMENTS_MESSAGE,
    find_appointment_slots_v2,
    resolve_booking_combo,
)
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


def find_slots_v2(center, payload):
    customer_profile = CustomerProfile.objects.get(pk=payload["customer_profile_id"])
    service = Service.objects.get(pk=payload["service_id"])
    slot_date = payload["date"]
    if isinstance(slot_date, str):
        slot_date = date.fromisoformat(slot_date)
    return find_appointment_slots_v2(
        center=center,
        customer_profile=customer_profile,
        service=service,
        modality=payload["modality"],
        slot_date=slot_date,
    )


def book_from_slot(center, actor, slot, customer_profile, service, modality):
    start, end = parse_slot_datetimes(slot)
    payload = {
        "customer_profile_id": str(customer_profile.pk),
        "service_id": str(service.pk),
        "modality": modality,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    if "doctor" in slot:
        payload["doctor_id"] = slot["doctor"]["id"]
    if "specialty" in slot:
        specialty = slot["specialty"]
        if isinstance(specialty, list):
            payload["specialty_id"] = [item["id"] for item in specialty]
        else:
            payload["specialty_id"] = specialty["id"]
    if "room" in slot:
        payload["room_id"] = slot["room"]["id"]
    if "equipment" in slot:
        payload["equipment_id"] = slot["equipment"]["id"]
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


class SlotsV2AutoAssignTests(TestCase):
    def setUp(self):
        self.center = Center.objects.create(
            name="Slots V2 Center",
            code="SL-V2",
            modes=AppointmentModes.BOTH,
        )
        seed_weekday_hours(self.center)
        self.doctor_role = create_role(self.center, "Doctor")
        self.coach_role = create_role(self.center, "Health Coach")
        self.nutrition_role = create_role(self.center, "Nutritionist")
        self.busy_coach = create_assigned_associate(
            self.center, "v2-busy-coach@example.com", self.coach_role
        )
        self.free_coach = create_assigned_associate(
            self.center, "v2-free-coach@example.com", self.coach_role
        )
        self.doctor = create_assigned_associate(
            self.center, "v2-doctor@example.com", self.doctor_role
        )
        self.actor = self.doctor.user
        self.customer_profile = create_customer_profile(
            self.center, "v2-patient@example.com"
        )
        self.service = Service.objects.create(
            name="V2 Auto Consult",
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
        self.busy_room = Room.objects.create(
            center=self.center,
            name="Busy Room",
            code="SL-V2-RM-BUSY",
            room_type_ref=self.room_type,
            is_active=True,
        )
        self.free_room = Room.objects.create(
            center=self.center,
            name="Free Room",
            code="SL-V2-RM-FREE",
            room_type_ref=self.room_type,
            is_active=True,
        )

    def virtual_payload(self):
        return {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.VIRTUAL,
            "date": SLOT_DATE.isoformat(),
        }

    def in_person_payload(self):
        return {
            "customer_profile_id": str(self.customer_profile.pk),
            "service_id": str(self.service.pk),
            "modality": AppointmentModes.IN_PERSON,
            "date": SLOT_DATE.isoformat(),
        }

    def book_busy_coach_morning(self):
        start = datetime.combine(SLOT_DATE, time(9, 0), tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        book_from_slot(
            self.center,
            self.actor,
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "specialty": {"id": str(self.busy_coach.pk)},
            },
            self.customer_profile,
            self.service,
            AppointmentModes.VIRTUAL,
        )

    def test_v2_rejects_preferred_key_silently_ignored_not_required(self):
        slots_payload = find_slots_v2(self.center, self.virtual_payload())
        slot = first_slot(slots_payload)
        self.assertIn("specialty", slot)
        self.assertNotIn("preferred", slot)
        self.assertNotIn("associates", slot)

    def test_v2_picks_least_busy_specialty(self):
        other_profile = create_customer_profile(
            self.center, "v2-other@example.com", first_name="Other"
        )
        start = datetime.combine(SLOT_DATE, time(9, 0), tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        book_from_slot(
            self.center,
            self.actor,
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "specialty": {"id": str(self.busy_coach.pk)},
            },
            other_profile,
            self.service,
            AppointmentModes.VIRTUAL,
        )
        slots_payload = find_slots_v2(self.center, self.virtual_payload())
        slot = first_slot(slots_payload)
        self.assertEqual(slot["specialty"]["id"], str(self.free_coach.pk))
        self.assertEqual(
            slot["specialty"]["role"]["id"], str(self.coach_role.pk)
        )

    def test_v2_picks_least_busy_room_and_equipment(self):
        equipment_type = EquipmentType.objects.create(
            center=self.center, name="Consult Device", is_active=True
        )
        busy_equipment = Equipment.objects.create(
            center=self.center,
            room=self.busy_room,
            equipment_type=equipment_type,
            name="Busy EQ",
            code="SL-V2-EQ-BUSY",
            serial_number="SN-V2-BUSY",
            is_active=True,
        )
        free_equipment = Equipment.objects.create(
            center=self.center,
            room=self.free_room,
            equipment_type=equipment_type,
            name="Free EQ",
            code="SL-V2-EQ-FREE",
            serial_number="SN-V2-FREE",
            is_active=True,
        )
        other_profile = create_customer_profile(
            self.center, "v2-room-busy@example.com", first_name="Room"
        )
        start = datetime.combine(SLOT_DATE, time(9, 0), tzinfo=KOLKATA)
        end = start + timedelta(minutes=30)
        book_from_slot(
            self.center,
            self.actor,
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "specialty": {"id": str(self.busy_coach.pk)},
                "room": {"id": str(self.busy_room.pk)},
                "equipment": {"id": str(busy_equipment.pk)},
            },
            other_profile,
            self.service,
            AppointmentModes.IN_PERSON,
        )
        slots_payload = find_slots_v2(self.center, self.in_person_payload())
        slot = first_slot(slots_payload)
        self.assertEqual(slot["room"]["id"], str(self.free_room.pk))
        self.assertEqual(slot["equipment"]["id"], str(free_equipment.pk))
        appointment = book_from_slot(
            self.center,
            self.actor,
            slot,
            self.customer_profile,
            self.service,
            AppointmentModes.IN_PERSON,
        )
        self.assertEqual(appointment.room.pk, self.free_room.pk)
        self.assertEqual(appointment.equipment.pk, free_equipment.pk)
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)

    def test_v2_doctor_and_specialty_roles(self):
        CenterServiceRoleRequirement.objects.create(
            assignment=self.assignment,
            role=self.doctor_role,
        )
        slots_payload = find_slots_v2(self.center, self.virtual_payload())
        slot = first_slot(slots_payload)
        self.assertEqual(slot["doctor"]["id"], str(self.doctor.pk))
        self.assertIn(slot["specialty"]["id"], {
            str(self.busy_coach.pk),
            str(self.free_coach.pk),
        })
        appointment = book_from_slot(
            self.center,
            self.actor,
            slot,
            self.customer_profile,
            self.service,
            AppointmentModes.VIRTUAL,
        )
        role_ids = set(
            appointment.associate_links.values_list("role_id", flat=True)
        )
        self.assertEqual(role_ids, {self.doctor_role.pk, self.coach_role.pk})

    def test_v2_multiple_specialty_roles_returns_array_and_books(self):
        nutritionist = create_assigned_associate(
            self.center, "v2-nutrition@example.com", self.nutrition_role
        )
        CenterServiceRoleRequirement.objects.create(
            assignment=self.assignment,
            role=self.nutrition_role,
        )
        slots_payload = find_slots_v2(self.center, self.virtual_payload())
        slot = first_slot(slots_payload)
        self.assertIsInstance(slot["specialty"], list)
        self.assertEqual(len(slot["specialty"]), 2)
        specialty_ids = {item["id"] for item in slot["specialty"]}
        self.assertIn(str(nutritionist.pk), specialty_ids)
        coach_ids = {str(self.busy_coach.pk), str(self.free_coach.pk)}
        self.assertEqual(len(specialty_ids & coach_ids), 1)
        role_names = {item["role"]["name"] for item in slot["specialty"]}
        self.assertEqual(role_names, {"Health Coach", "Nutritionist"})
        appointment = book_from_slot(
            self.center,
            self.actor,
            slot,
            self.customer_profile,
            self.service,
            AppointmentModes.VIRTUAL,
        )
        role_ids = set(
            appointment.associate_links.values_list("role_id", flat=True)
        )
        self.assertEqual(role_ids, {self.coach_role.pk, self.nutrition_role.pk})

    def test_v2_rejects_missing_role_requirements(self):
        CenterServiceRoleRequirement.objects.filter(
            assignment=self.assignment
        ).delete()
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots_v2(self.center, self.virtual_payload())
        self.assertIn(
            AUTO_ASSIGN_NO_ROLE_REQUIREMENTS_MESSAGE,
            raised.exception.messages,
        )

    def test_v2_rejects_in_person_without_room_types(self):
        CenterServiceRoomTypeRequirement.objects.filter(
            assignment=self.assignment
        ).delete()
        with self.assertRaises(DjangoValidationError) as raised:
            find_slots_v2(self.center, self.in_person_payload())
        self.assertIn(
            AUTO_ASSIGN_NO_ROOM_TYPE_REQUIREMENTS_MESSAGE,
            raised.exception.messages,
        )

    def test_slot_serializer_rejects_past_date(self):
        payload = self.virtual_payload()
        payload["date"] = (timezone.localdate() - timedelta(days=1)).isoformat()
        payload["preferred"] = {"specialty_id": str(self.free_coach.pk)}
        serializer = AppointmentSlotFindSerializer(
            data=payload,
            context={"center": self.center},
        )
        with self.assertRaises(DRFValidationError):
            serializer.is_valid(raise_exception=True)
