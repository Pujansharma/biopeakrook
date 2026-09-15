from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.associates.utils.roles import (
    assignment_active_roles,
    assignment_holds_role,
)
from accounts.customers.models import CustomerCenterAssignment
from appointments.models import Appointment
from appointments.utils.calendar import (
    associate_block_intervals_by_associate,
    associate_leave_intervals_by_associate,
    collect_associate_block_events,
    collect_associate_leave_events,
    collect_care_team_block_events,
    collect_closure_events,
    collect_equipment_block_events,
    collect_equipment_downtime_events,
    collect_room_block_events,
    collect_room_downtime_events,
    expand_center_operating_hours,
    expand_roster_entries,
    expand_roster_entries_for_associates,
    get_center_timezone_name,
    team_block_intervals_by_associate,
)
from appointments.utils.care_teams import (
    expand_care_team_for_assignment,
    live_associate_center_assignments,
    live_care_teams_for_associate,
)
from appointments.utils.constants import BUSY_APPOINTMENT_STATUSES
from appointments.utils.intervals import (
    datetime_range_for_dates,
    intersect_intervals,
    merge_intervals,
    split_into_slots,
    subtract_intervals,
)
from core.utils.constants import AppointmentModes
from inventory.models import Equipment, Room
from programs.services.models import CenterServiceAssignment

SLOT_CAP_PER_DAY = 200
ASSOCIATES_REQUIRED_FOR_BOOKING = (
    "At least one associate is required. Send care_team_id "
    "and/or doctor_id / specialty_id."
)
HEALTH_COACH_ID_REJECT_MESSAGE = (
    "Use specialty_id instead of health_coach_id."
)
PREFERRED_REQUIRED_MESSAGE = "preferred is required."
STAFF_REQUIRED_MESSAGE = (
    "care_team_id and/or doctor_id/specialty_id is required."
)
CARE_TEAM_XOR_MESSAGE = (
    "care_team_id cannot be combined with doctor_id or specialty_id."
)
SAME_DOCTOR_AND_SPECIALTY_MESSAGE = (
    "doctor_id and specialty_id cannot refer to the same associate."
)
ROOM_REQUIRED_IN_PERSON_MESSAGE = (
    "room_id is required for in-person appointments."
)
ROOM_NOT_ALLOWED_VIRTUAL_MESSAGE = (
    "room_id is not allowed for virtual appointments."
)
ROOM_TYPE_INACTIVE_MESSAGE = "Room does not have an active room type."
ROOM_TYPE_NOT_MAPPED_MESSAGE = "Room type is not mapped to this service."
EQUIPMENT_REQUIRED_FOR_ROOM_MESSAGE = (
    "equipment_id is required when the selected room has bookable equipment."
)
EQUIPMENT_NOT_ALLOWED_EMPTY_ROOM_MESSAGE = (
    "equipment_id is not allowed when the selected room has no bookable equipment."
)
EQUIPMENT_NOT_ALLOWED_VIRTUAL_MESSAGE = (
    "equipment_id is not allowed for virtual appointments."
)
EQUIPMENT_NOT_ON_ROOM_MESSAGE = (
    "equipment_id must belong to the selected room."
)
EQUIPMENT_INACTIVE_MESSAGE = "Equipment is inactive."
EQUIPMENT_TYPE_INACTIVE_MESSAGE = "Equipment type is inactive."
MISSING_DOCTOR_ROLE_MESSAGE = (
    "doctor_id must hold a live role with doctor in the role name."
)
MISSING_SPECIALTY_ROLE_MESSAGE = (
    "specialty_id must hold a live non-doctor role mapped to this service."
)
AMBIGUOUS_DOCTOR_ROLE_MESSAGE = (
    "doctor_id matches more than one live doctor role."
)


def compute_exclusive_bounds(start, end, buffer_before, buffer_after):
    exclusive_start = start - timedelta(minutes=buffer_before)
    exclusive_end = end + timedelta(minutes=buffer_after)
    return exclusive_start, exclusive_end


def interval_overlaps_any(interval_start, interval_end, busy_intervals):
    for busy_start, busy_end in busy_intervals:
        if interval_start < busy_end and interval_end > busy_start:
            return True
    return False


def is_interval_contained_in_windows(interval_start, interval_end, windows):
    for window_start, window_end in windows:
        if interval_start >= window_start and interval_end <= window_end:
            return True
    return False


def modality_compatible(assignment_modality, requested_modality):
    if assignment_modality == AppointmentModes.BOTH:
        return True
    return assignment_modality == requested_modality


def associate_modality_compatible(assignment_mode, requested_modality):
    if assignment_mode == AppointmentModes.BOTH:
        return True
    return assignment_mode == requested_modality


def get_associate_display_name(associate):
    user = associate.user
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    return name or str(associate.pk)


def get_customer_profile_display_name(customer_profile):
    parts = [customer_profile.first_name or "", customer_profile.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    return name or str(customer_profile.pk)


def load_busy_interval_maps(center, range_start, range_end):
    appointments = (
        Appointment.objects.filter(
            center=center,
            status__in=BUSY_APPOINTMENT_STATUSES,
            exclusive_start_datetime__lt=range_end,
            exclusive_end_datetime__gt=range_start,
        )
        .prefetch_related("associate_links")
        .select_related("room", "equipment")
    )
    associate_map = {}
    room_map = {}
    equipment_map = {}
    for appointment in appointments:
        exclusive_interval = (
            appointment.exclusive_start_datetime,
            appointment.exclusive_end_datetime,
        )
        if appointment.room_id:
            room_key = str(appointment.room_id)
            room_map.setdefault(room_key, []).append(exclusive_interval)
        if appointment.equipment_id:
            equipment_key = str(appointment.equipment_id)
            equipment_map.setdefault(equipment_key, []).append(exclusive_interval)
        for link in appointment.associate_links.all():
            associate_key = str(link.associate_id)
            associate_map.setdefault(associate_key, []).append(exclusive_interval)
    return {
        "associate": associate_map,
        "room": room_map,
        "equipment": equipment_map,
    }


def load_customer_busy_intervals(customer_profile, range_start, range_end):
    appointments = Appointment.objects.filter(
        customer_profile=customer_profile,
        status__in=BUSY_APPOINTMENT_STATUSES,
        exclusive_start_datetime__lt=range_end,
        exclusive_end_datetime__gt=range_start,
    )
    intervals = []
    for appointment in appointments:
        intervals.append(
            (
                appointment.exclusive_start_datetime,
                appointment.exclusive_end_datetime,
            )
        )
    return intervals


def get_center_service_assignment(center, service):
    return (
        CenterServiceAssignment.objects.filter(
            center=center,
            service=service,
            is_active=True,
        )
        .prefetch_related(
            "role_requirements__role",
            "room_type_requirements__room_type",
        )
        .first()
    )


def validate_customer_profile_for_center(customer_profile, center):
    if not customer_profile.is_active:
        raise ValidationError("Customer profile is inactive.")
    has_assignment = CustomerCenterAssignment.objects.filter(
        customer_profile=customer_profile,
        center=center,
        is_active=True,
    ).exists()
    if not has_assignment:
        raise ValidationError(
            "Customer profile is not assigned to this center."
        )


def role_is_doctor(role):
    return "doctor" in (role.name or "").lower()


def pick_unique_role(roles, empty_message, ambiguous_message):
    if not roles:
        raise ValidationError(empty_message)
    if len(roles) > 1:
        raise ValidationError(ambiguous_message)
    return roles[0]


def pick_doctor_role(roles):
    return pick_unique_role(
        [role for role in roles if role_is_doctor(role)],
        MISSING_DOCTOR_ROLE_MESSAGE,
        AMBIGUOUS_DOCTOR_ROLE_MESSAGE,
    )


def mapped_service_role_ids(service_assignment):
    if service_assignment is None:
        return set()
    role_ids = set()
    for requirement in service_assignment.role_requirements.all():
        if not requirement.is_active:
            continue
        if not requirement.role.is_active:
            continue
        role_ids.add(requirement.role.pk)
    return role_ids


def role_pk_sort_key(role):
    return str(role.pk)


def pick_specialty_role(roles, service_assignment=None):
    mapped_role_ids = mapped_service_role_ids(service_assignment)
    matching_roles = [
        role
        for role in roles
        if not role_is_doctor(role) and role.pk in mapped_role_ids
    ]
    if not matching_roles:
        raise ValidationError(MISSING_SPECIALTY_ROLE_MESSAGE)
    matching_roles.sort(key=role_pk_sort_key)
    return matching_roles[0]


def pick_preferred_person_role(preferred_key, live_roles, service_assignment):
    if preferred_key == "specialty_id":
        return pick_specialty_role(live_roles, service_assignment)
    if preferred_key == "doctor_id":
        return pick_doctor_role(live_roles)
    raise ValidationError(f"Unknown preferred person key: {preferred_key}")


def required_room_types_for_assignment(assignment):
    room_types = []
    for link in assignment.room_type_requirements.all():
        if not link.is_active:
            continue
        if not link.room_type.is_active:
            continue
        room_types.append(link.room_type)
    return room_types


def room_matches_assignment_types(assignment, room):
    required = required_room_types_for_assignment(assignment)
    if not required:
        return True
    if room.room_type_ref is None:
        return False
    required_ids = {room_type.pk for room_type in required}
    return room.room_type_ref.pk in required_ids


def validate_room_for_assignment(room, center, assignment=None):
    if room is None:
        return
    if room.center.pk != center.pk:
        raise ValidationError("Room does not belong to this center.")
    if not room.is_active:
        raise ValidationError("Preferred room is invalid or inactive.")
    room_type = room.room_type_ref
    if room_type is None or not room_type.is_active:
        raise ValidationError(ROOM_TYPE_INACTIVE_MESSAGE)
    if assignment is not None and not room_matches_assignment_types(
        assignment, room
    ):
        raise ValidationError(ROOM_TYPE_NOT_MAPPED_MESSAGE)


def reject_health_coach_id(preferred):
    if preferred and "health_coach_id" in preferred:
        raise ValidationError({"health_coach_id": HEALTH_COACH_ID_REJECT_MESSAGE})


def validate_preferred_combo(preferred, modality):
    reject_health_coach_id(preferred)
    preferred = preferred or {}
    care_team_id = preferred.get("care_team_id")
    doctor_id = preferred.get("doctor_id")
    specialty_id = preferred.get("specialty_id")
    room_id = preferred.get("room_id")
    has_person = bool(care_team_id or doctor_id or specialty_id)
    if not has_person:
        raise ValidationError(
            {
                "care_team_id": STAFF_REQUIRED_MESSAGE,
                "doctor_id": STAFF_REQUIRED_MESSAGE,
                "specialty_id": STAFF_REQUIRED_MESSAGE,
            }
        )
    if care_team_id and (doctor_id or specialty_id):
        raise ValidationError({"care_team_id": CARE_TEAM_XOR_MESSAGE})
    equipment_id = preferred.get("equipment_id")
    if modality == AppointmentModes.IN_PERSON:
        if not room_id:
            raise ValidationError({"room_id": ROOM_REQUIRED_IN_PERSON_MESSAGE})
    else:
        if room_id:
            raise ValidationError({"room_id": ROOM_NOT_ALLOWED_VIRTUAL_MESSAGE})
        if equipment_id:
            raise ValidationError(
                {"equipment_id": EQUIPMENT_NOT_ALLOWED_VIRTUAL_MESSAGE}
            )
    if doctor_id and specialty_id and str(doctor_id) == str(specialty_id):
        raise ValidationError(
            {
                "doctor_id": SAME_DOCTOR_AND_SPECIALTY_MESSAGE,
                "specialty_id": SAME_DOCTOR_AND_SPECIALTY_MESSAGE,
            }
        )


def compute_associate_free_windows(
    center,
    associate,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
    team_block_intervals=None,
    center_hours=None,
    closure_intervals=None,
    roster_hours=None,
    block_intervals=None,
    leave_intervals=None,
):
    if center_hours is None:
        center_hours = expand_center_operating_hours(
            center, query_start, query_end, timezone_name
        )
    if roster_hours is None:
        roster_hours = expand_roster_entries(
            center, associate, query_start, query_end, timezone_name
        )
    base_intervals = intersect_intervals(center_hours, roster_hours)
    if block_intervals is None:
        block_intervals, _ = collect_associate_block_events(
            center, associate, query_start, query_end, timezone_name
        )
    if leave_intervals is None:
        leave_intervals, _ = collect_associate_leave_events(
            center, associate, query_start, query_end, timezone_name
        )
    if closure_intervals is None:
        closure_intervals, _ = collect_closure_events(
            center, query_start, query_end, timezone_name
        )
    if team_block_intervals is None:
        care_teams = live_care_teams_for_associate(center, associate)
        team_block_intervals, _ = collect_care_team_block_events(
            center, care_teams, query_start, query_end, timezone_name
        )
    associate_busy = appointment_busy_map.get(str(associate.pk), [])
    busy_intervals = merge_intervals(
        block_intervals
        + leave_intervals
        + closure_intervals
        + team_block_intervals
        + associate_busy
    )
    return subtract_intervals(base_intervals, busy_intervals)


def compute_room_free_windows(
    center,
    room,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
    center_hours=None,
    closure_intervals=None,
):
    if center_hours is None:
        center_hours = expand_center_operating_hours(
            center, query_start, query_end, timezone_name
        )
    base_intervals = center_hours
    block_intervals, _ = collect_room_block_events(
        room, query_start, query_end, timezone_name
    )
    downtime_intervals, _ = collect_room_downtime_events(
        room, query_start, query_end, timezone_name
    )
    if closure_intervals is None:
        closure_intervals, _ = collect_closure_events(
            center, query_start, query_end, timezone_name
        )
    room_busy = appointment_busy_map.get(str(room.pk), [])
    busy_intervals = merge_intervals(
        block_intervals + downtime_intervals + closure_intervals + room_busy
    )
    return subtract_intervals(base_intervals, busy_intervals)


def compute_equipment_free_windows(
    center,
    equipment,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
    center_hours=None,
    closure_intervals=None,
):
    if center_hours is None:
        center_hours = expand_center_operating_hours(
            center, query_start, query_end, timezone_name
        )
    base_intervals = center_hours
    block_intervals, _ = collect_equipment_block_events(
        equipment, query_start, query_end, timezone_name
    )
    downtime_intervals, _ = collect_equipment_downtime_events(
        equipment, query_start, query_end, timezone_name
    )
    if closure_intervals is None:
        closure_intervals, _ = collect_closure_events(
            center, query_start, query_end, timezone_name
        )
    equipment_busy = appointment_busy_map.get(str(equipment.pk), [])
    busy_intervals = merge_intervals(
        block_intervals + downtime_intervals + closure_intervals + equipment_busy
    )
    return subtract_intervals(base_intervals, busy_intervals)


def unique_associates_from_resource_pools(resource_pools):
    associates = []
    seen_ids = set()
    for role_pool in resource_pools["roles"]:
        for associate in role_pool["associates"]:
            if associate.pk in seen_ids:
                continue
            seen_ids.add(associate.pk)
            associates.append(associate)
    for associate in resource_pools.get("extra_associates", []):
        if associate.pk in seen_ids:
            continue
        seen_ids.add(associate.pk)
        associates.append(associate)
    return associates


def build_resource_free_window_cache(
    center,
    resource_pools,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
):
    associates = unique_associates_from_resource_pools(resource_pools)
    center_hours = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    roster_by_associate = expand_roster_entries_for_associates(
        center, associates, query_start, query_end, timezone_name
    )
    blocks_by_associate = associate_block_intervals_by_associate(
        center, associates, query_start, query_end, timezone_name
    )
    leaves_by_associate = associate_leave_intervals_by_associate(
        center, associates, query_start, query_end, timezone_name
    )
    team_blocks_by_associate = team_block_intervals_by_associate(
        center, associates, query_start, query_end, timezone_name
    )
    associate_windows = {}
    for associate in associates:
        associate_windows[str(associate.pk)] = compute_associate_free_windows(
            center,
            associate,
            query_start,
            query_end,
            timezone_name,
            appointment_busy_map["associate"],
            team_block_intervals=team_blocks_by_associate.get(associate.pk, []),
            center_hours=center_hours,
            closure_intervals=closure_intervals,
            roster_hours=roster_by_associate.get(associate.pk, []),
            block_intervals=blocks_by_associate.get(associate.pk, []),
            leave_intervals=leaves_by_associate.get(associate.pk, []),
        )
    room_windows = {}
    for room in resource_pools["rooms"]:
        room_windows[str(room.pk)] = compute_room_free_windows(
            center,
            room,
            query_start,
            query_end,
            timezone_name,
            appointment_busy_map["room"],
            center_hours=center_hours,
            closure_intervals=closure_intervals,
        )
    equipment_windows = {}
    for equipment in resource_pools["equipment"]:
        equipment_windows[str(equipment.pk)] = compute_equipment_free_windows(
            center,
            equipment,
            query_start,
            query_end,
            timezone_name,
            appointment_busy_map["equipment"],
            center_hours=center_hours,
            closure_intervals=closure_intervals,
        )
    return {
        "associate": associate_windows,
        "room": room_windows,
        "equipment": equipment_windows,
    }


def preferred_room_id(preferred):
    if not preferred:
        return None
    return preferred.get("room_id")


def room_has_bookable_equipment(room):
    if room is None:
        return False
    return Equipment.objects.filter(
        room=room,
        is_active=True,
        center=room.center,
        equipment_type__isnull=False,
        equipment_type__is_active=True,
    ).exists()


def resolve_preferred_equipment(room, preferred):
    preferred_equipment_id = (preferred or {}).get("equipment_id")
    if not room_has_bookable_equipment(room):
        if preferred_equipment_id:
            raise ValidationError(EQUIPMENT_NOT_ALLOWED_EMPTY_ROOM_MESSAGE)
        return None
    if not preferred_equipment_id:
        raise ValidationError(EQUIPMENT_REQUIRED_FOR_ROOM_MESSAGE)
    equipment = (
        Equipment.objects.filter(
            pk=preferred_equipment_id,
            room=room,
            center=room.center,
        )
        .select_related("equipment_type")
        .first()
    )
    if equipment is None:
        raise ValidationError(EQUIPMENT_NOT_ON_ROOM_MESSAGE)
    if not equipment.is_active:
        raise ValidationError(EQUIPMENT_INACTIVE_MESSAGE)
    equipment_type = equipment.equipment_type
    if equipment_type is None or not equipment_type.is_active:
        raise ValidationError(EQUIPMENT_TYPE_INACTIVE_MESSAGE)
    return equipment


def resolve_equipment_for_room(room, resource_pools=None):
    if room is None:
        return None
    by_room = (resource_pools or {}).get("equipment_by_room_id") or {}
    return by_room.get(str(room.pk))


def resource_is_free(resource_type, resource_id, exclusive_start, exclusive_end, free_window_cache):
    windows = free_window_cache[resource_type].get(str(resource_id), [])
    return is_interval_contained_in_windows(
        exclusive_start, exclusive_end, windows
    )


def get_live_assignment_for_associate(center, associate_id, modality):
    assignment = (
        live_associate_center_assignments(center, [associate_id])
        .first()
    )
    if assignment is None:
        raise ValidationError(
            "Associate is not assigned to this center with an active role."
        )
    if not associate_modality_compatible(assignment.mode, modality):
        raise ValidationError("Associate modality is not compatible.")
    return assignment


def ensure_associate_free(
    associate,
    exclusive_start,
    exclusive_end,
    free_window_cache,
    soft=False,
):
    if resource_is_free(
        "associate",
        associate.pk,
        exclusive_start,
        exclusive_end,
        free_window_cache,
    ):
        return True
    if soft:
        return False
    raise ValidationError("Selected associate is not available.")


def collect_preferred_person_ids(preferred):
    if not preferred:
        return []
    person_ids = []
    for key in ("doctor_id", "specialty_id"):
        value = preferred.get(key)
        if value:
            person_ids.append(str(value))
    return person_ids


def resolve_preferred_person_entry(
    center, preferred_key, associate_id, modality, service_assignment=None
):
    center_assignment = get_live_assignment_for_associate(
        center, associate_id, modality
    )
    live_roles = assignment_active_roles(center_assignment)
    role = pick_preferred_person_role(
        preferred_key, live_roles, service_assignment
    )
    return {
        "role_id": str(role.pk),
        "associate_id": center_assignment.associate.pk,
        "associate": center_assignment.associate,
        "role": role,
    }


def build_resolve_resource_pools(center, assignment, modality, preferred):
    """Preference-only pools: no leftover fill from service role/room requirements."""
    preferred = preferred or {}
    validate_preferred_combo(preferred, modality)
    resource_pools = {
        "roles": [],
        "rooms": [],
        "equipment": [],
        "equipment_by_room_id": {},
        "extra_associates": [],
        "care_team": None,
        "preferred_entries": [],
    }

    care_team_id = preferred.get("care_team_id")
    if care_team_id:
        care_team_members = expand_care_team_for_assignment(center, care_team_id)
        if not care_team_members:
            raise ValidationError(
                "Care team has no live members at this center."
            )
        resource_pools["care_team"] = care_team_members[0].care_team
        for member in care_team_members:
            resource_pools["extra_associates"].append(member.associate)
            resource_pools["preferred_entries"].append(
                {
                    "role_id": str(member.role.pk),
                    "associate_id": member.associate.pk,
                    "associate": member.associate,
                    "role": member.role,
                }
            )

    if preferred.get("doctor_id"):
        entry = resolve_preferred_person_entry(
            center, "doctor_id", preferred["doctor_id"], modality
        )
        resource_pools["extra_associates"].append(entry["associate"])
        resource_pools["preferred_entries"].append(entry)
    if preferred.get("specialty_id"):
        entry = resolve_preferred_person_entry(
            center,
            "specialty_id",
            preferred["specialty_id"],
            modality,
            service_assignment=assignment,
        )
        resource_pools["extra_associates"].append(entry["associate"])
        resource_pools["preferred_entries"].append(entry)

    seen_associate_ids = set()
    unique_associates = []
    for associate in resource_pools["extra_associates"]:
        key = str(associate.pk)
        if key in seen_associate_ids:
            raise ValidationError(
                "Same associate cannot appear on an appointment more than once."
            )
        seen_associate_ids.add(key)
        unique_associates.append(associate)
    resource_pools["extra_associates"] = unique_associates

    preferred_id = preferred_room_id(preferred)
    if modality == AppointmentModes.IN_PERSON:
        preferred_room = (
            Room.objects.filter_active(center=center, pk=preferred_id)
            .select_related("room_type_ref")
            .first()
        )
        if preferred_room is None:
            raise ValidationError("Preferred room is invalid or inactive.")
        validate_room_for_assignment(preferred_room, center, assignment)
        resource_pools["rooms"] = [preferred_room]
        equipment = resolve_preferred_equipment(preferred_room, preferred)
        resource_pools["equipment"] = [equipment] if equipment is not None else []
        resource_pools["equipment_by_room_id"] = {
            str(preferred_room.pk): equipment
        }
    return resource_pools


def ensure_free_windows_for_pools(
    center,
    resource_pools,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
    free_window_cache,
):
    missing_associates = [
        associate
        for associate in resource_pools.get("extra_associates", [])
        if str(associate.pk) not in free_window_cache["associate"]
    ]
    if missing_associates:
        center_hours = expand_center_operating_hours(
            center, query_start, query_end, timezone_name
        )
        closure_intervals, _ = collect_closure_events(
            center, query_start, query_end, timezone_name
        )
        roster_by_associate = expand_roster_entries_for_associates(
            center, missing_associates, query_start, query_end, timezone_name
        )
        blocks_by_associate = associate_block_intervals_by_associate(
            center, missing_associates, query_start, query_end, timezone_name
        )
        leaves_by_associate = associate_leave_intervals_by_associate(
            center, missing_associates, query_start, query_end, timezone_name
        )
        team_blocks_by_associate = team_block_intervals_by_associate(
            center, missing_associates, query_start, query_end, timezone_name
        )
        for associate in missing_associates:
            free_window_cache["associate"][str(associate.pk)] = (
                compute_associate_free_windows(
                    center,
                    associate,
                    query_start,
                    query_end,
                    timezone_name,
                    appointment_busy_map["associate"],
                    team_block_intervals=team_blocks_by_associate.get(
                        associate.pk, []
                    ),
                    center_hours=center_hours,
                    closure_intervals=closure_intervals,
                    roster_hours=roster_by_associate.get(associate.pk, []),
                    block_intervals=blocks_by_associate.get(associate.pk, []),
                    leave_intervals=leaves_by_associate.get(associate.pk, []),
                )
            )
    for room in resource_pools["rooms"]:
        room_key = str(room.pk)
        if room_key not in free_window_cache["room"]:
            free_window_cache["room"][room_key] = compute_room_free_windows(
                center,
                room,
                query_start,
                query_end,
                timezone_name,
                appointment_busy_map["room"],
            )
    for equipment in resource_pools["equipment"]:
        equipment_key = str(equipment.pk)
        if equipment_key not in free_window_cache["equipment"]:
            free_window_cache["equipment"][equipment_key] = (
                compute_equipment_free_windows(
                    center,
                    equipment,
                    query_start,
                    query_end,
                    timezone_name,
                    appointment_busy_map["equipment"],
                )
            )


def resolve_appointment_combo(
    center,
    assignment,
    modality,
    preferred,
    exclusive_start,
    exclusive_end,
    free_window_cache,
    appointment_busy_map,
    resource_pools=None,
    query_start=None,
    query_end=None,
    timezone_name=None,
    soft=False,
):
    preferred = preferred or {}
    if resource_pools is None:
        resource_pools = build_resolve_resource_pools(
            center, assignment, modality, preferred
        )
    if query_start is not None and timezone_name is not None:
        ensure_free_windows_for_pools(
            center,
            resource_pools,
            query_start,
            query_end,
            timezone_name,
            appointment_busy_map,
            free_window_cache,
        )

    associates_payload = []
    used_associate_ids = set()
    care_team = resource_pools.get("care_team")

    for entry in resource_pools.get("preferred_entries") or []:
        associate = entry["associate"]
        if not ensure_associate_free(
            associate,
            exclusive_start,
            exclusive_end,
            free_window_cache,
            soft=soft,
        ):
            return None
        associate_key = str(associate.pk)
        if associate_key in used_associate_ids:
            if soft:
                return None
            raise ValidationError(
                "Same associate cannot appear on an appointment more than once."
            )
        used_associate_ids.add(associate_key)
        associates_payload.append(
            {
                "role_id": entry["role_id"],
                "associate_id": associate.pk,
            }
        )

    if not associates_payload:
        if soft:
            return None
        raise ValidationError(ASSOCIATES_REQUIRED_FOR_BOOKING)

    room = None
    equipment = None
    if modality == AppointmentModes.IN_PERSON:
        rooms = resource_pools.get("rooms") or []
        if not rooms:
            if soft:
                return None
            raise ValidationError("A room is required for in-person appointments.")
        room = rooms[0]
        if not resource_is_free(
            "room",
            room.pk,
            exclusive_start,
            exclusive_end,
            free_window_cache,
        ):
            if soft:
                return None
            raise ValidationError("Selected room is not available.")
        equipment = resolve_equipment_for_room(room, resource_pools)
        if equipment is not None and not resource_is_free(
            "equipment",
            equipment.pk,
            exclusive_start,
            exclusive_end,
            free_window_cache,
        ):
            if soft:
                return None
            raise ValidationError("Selected equipment is not available.")

    return {
        "associates": associates_payload,
        "room": room,
        "equipment": equipment,
        "care_team": care_team,
        "preferred_entries": resource_pools.get("preferred_entries") or [],
    }


def serialize_named_resource(resource):
    return {"id": str(resource.pk), "name": resource.name}


def serialize_slot_person(associate):
    return {
        "id": str(associate.pk),
        "name": get_associate_display_name(associate),
    }


def serialize_slot_specialty(associate, role):
    payload = serialize_slot_person(associate)
    payload["role"] = {"id": str(role.pk), "name": role.name}
    return payload


def preferred_entry_for_associate(entries, associate_id):
    associate_key = str(associate_id)
    for entry in entries:
        if str(entry["associate_id"]) == associate_key:
            return entry
    return None


def serialize_pinned_slot(slot_start, slot_end, combo, preferred=None):
    preferred = preferred or {}
    payload = {
        "start": slot_start.isoformat(),
        "end": slot_end.isoformat(),
    }
    entries = combo.get("preferred_entries") or []
    if preferred.get("care_team_id"):
        care_team = combo.get("care_team")
        if care_team is not None:
            payload["care_team"] = serialize_named_resource(care_team)
    doctor_id = preferred.get("doctor_id")
    if doctor_id:
        entry = preferred_entry_for_associate(entries, doctor_id)
        if entry is not None:
            payload["doctor"] = serialize_slot_person(entry["associate"])
    specialty_id = preferred.get("specialty_id")
    if specialty_id:
        entry = preferred_entry_for_associate(entries, specialty_id)
        if entry is not None:
            payload["specialty"] = serialize_slot_specialty(
                entry["associate"], entry["role"]
            )
    room = combo.get("room")
    if room is not None:
        payload["room"] = serialize_named_resource(room)
    equipment = combo.get("equipment")
    if equipment is not None:
        payload["equipment"] = serialize_named_resource(equipment)
    return payload


def find_appointment_slots(
    center,
    customer_profile,
    service,
    modality,
    slot_date,
    preferred=None,
):
    validate_customer_profile_for_center(customer_profile, center)
    assignment = get_center_service_assignment(center, service)
    if assignment is None:
        raise ValidationError("Service is not available at this center.")
    if not modality_compatible(assignment.modality, modality):
        raise ValidationError("Modality is not supported for this service.")
    if not assignment.duration:
        raise ValidationError("Service duration is not configured for this center.")

    if not preferred:
        raise ValidationError(PREFERRED_REQUIRED_MESSAGE)
    validate_preferred_combo(preferred, modality)

    resource_pools = build_resolve_resource_pools(
        center, assignment, modality, preferred
    )

    timezone_name = get_center_timezone_name(center)
    query_start = slot_date
    query_end = slot_date
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    busy_maps = load_busy_interval_maps(center, range_start, range_end)
    customer_busy = load_customer_busy_intervals(
        customer_profile, range_start, range_end
    )

    free_window_cache = build_resource_free_window_cache(
        center,
        resource_pools,
        query_start,
        query_end,
        timezone_name,
        busy_maps,
    )

    center_hours = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    base_windows = subtract_intervals(center_hours, closure_intervals)

    duration_minutes = assignment.duration
    buffer_before = assignment.buffer_before
    buffer_after = assignment.buffer_after
    step_minutes = duration_minutes + buffer_before + buffer_after
    candidate_slots = split_into_slots(
        base_windows, duration_minutes, step_minutes
    )

    now = timezone.now()
    slots = []
    truncated = False
    for slot_start, slot_end in candidate_slots:
        if slot_start < now:
            continue
        exclusive_start, exclusive_end = compute_exclusive_bounds(
            slot_start,
            slot_end,
            buffer_before,
            buffer_after,
        )
        if interval_overlaps_any(exclusive_start, exclusive_end, customer_busy):
            continue
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, base_windows
        ):
            continue
        combo = resolve_appointment_combo(
            center,
            assignment,
            modality,
            preferred,
            exclusive_start,
            exclusive_end,
            free_window_cache,
            busy_maps,
            resource_pools=resource_pools,
            query_start=query_start,
            query_end=query_end,
            timezone_name=timezone_name,
            soft=True,
        )
        if combo is None:
            continue
        slots.append(serialize_pinned_slot(slot_start, slot_end, combo, preferred))
        if len(slots) >= SLOT_CAP_PER_DAY:
            if len(candidate_slots) > len(slots):
                truncated = True
            break

    return {
        "date": slot_date.isoformat(),
        "timezone": timezone_name,
        "duration_minutes": duration_minutes,
        "buffer_before_minutes": buffer_before,
        "buffer_after_minutes": buffer_after,
        "slots": slots,
        "truncated": truncated,
    }


def validate_associate_assignments(center, associates_payload, modality):
    provided_role_ids = set()
    seen_associate_ids = set()
    associate_ids = [entry["associate_id"] for entry in associates_payload]
    assignments_by_associate = {
        str(assignment.associate.pk): assignment
        for assignment in live_associate_center_assignments(center, associate_ids)
    }
    for entry in associates_payload:
        role_id = str(entry["role_id"])
        associate_id = str(entry["associate_id"])
        if role_id in provided_role_ids:
            raise ValidationError("Duplicate role on this appointment.")
        if associate_id in seen_associate_ids:
            raise ValidationError("Duplicate associate on this appointment.")
        provided_role_ids.add(role_id)
        seen_associate_ids.add(associate_id)
        assignment = assignments_by_associate.get(associate_id)
        if assignment is None or not assignment_holds_role(assignment, role_id):
            raise ValidationError(
                "Associate is not assigned to this center with the required role."
            )
        if not associate_modality_compatible(assignment.mode, modality):
            raise ValidationError("Associate modality is not compatible.")


def validate_appointment_allocation(
    center,
    assignment,
    modality,
    start,
    end,
    associates,
    room,
    equipment,
    customer_profile=None,
    exclude_appointment=None,
):
    """Duration, staff roles, customer overlap. Free windows already checked."""
    if customer_profile is not None:
        validate_customer_profile_for_center(customer_profile, center)
    if not modality_compatible(assignment.modality, modality):
        raise ValidationError("Modality is not supported for this service.")
    if not assignment.duration:
        raise ValidationError("Service duration is not configured for this center.")

    expected_end = start + timedelta(minutes=assignment.duration)
    if end != expected_end:
        raise ValidationError(
            "Appointment end time does not match configured duration."
        )

    if associates:
        validate_associate_assignments(center, associates, modality)

    if modality == AppointmentModes.IN_PERSON:
        if room is None:
            raise ValidationError(
                "A room is required for in-person appointments."
            )
    elif room is not None or equipment is not None:
        raise ValidationError(
            "Room and equipment must not be set for virtual appointments."
        )

    if customer_profile is None:
        return

    exclusive_start, exclusive_end = compute_exclusive_bounds(
        start, end, assignment.buffer_before, assignment.buffer_after
    )
    customer_busy = load_customer_busy_intervals(
        customer_profile, exclusive_start, exclusive_end
    )
    if exclude_appointment is not None:
        exclusive_interval = (
            exclude_appointment.exclusive_start_datetime,
            exclude_appointment.exclusive_end_datetime,
        )
        customer_busy = [
            item for item in customer_busy if item != exclusive_interval
        ]
    if interval_overlaps_any(exclusive_start, exclusive_end, customer_busy):
        raise ValidationError(
            "Customer already has an appointment during this time."
        )


def resolve_booking_combo(
    center,
    assignment,
    modality,
    preferred,
    start,
    end,
    customer_profile=None,
    exclude_appointment=None,
):
    """Resolve staff/room/equipment from preferred IDs, then validate free."""
    preferred = preferred or {}
    if not preferred:
        raise ValidationError(PREFERRED_REQUIRED_MESSAGE)
    validate_preferred_combo(preferred, modality)
    buffer_before = assignment.buffer_before
    buffer_after = assignment.buffer_after
    exclusive_start, exclusive_end = compute_exclusive_bounds(
        start, end, buffer_before, buffer_after
    )
    timezone_name = get_center_timezone_name(center)
    slot_date = start.astimezone(ZoneInfo(timezone_name)).date()

    busy_maps = load_busy_interval_maps(center, exclusive_start, exclusive_end)
    if exclude_appointment is not None:
        busy_maps = _subtract_appointment_from_busy_maps(
            busy_maps, exclude_appointment
        )
    resource_pools = build_resolve_resource_pools(
        center, assignment, modality, preferred
    )
    free_window_cache = build_resource_free_window_cache(
        center,
        resource_pools,
        slot_date,
        slot_date,
        timezone_name,
        busy_maps,
    )
    combo = resolve_appointment_combo(
        center,
        assignment,
        modality,
        preferred,
        exclusive_start,
        exclusive_end,
        free_window_cache,
        busy_maps,
        resource_pools=resource_pools,
        query_start=slot_date,
        query_end=slot_date,
        timezone_name=timezone_name,
        soft=False,
    )
    associates = combo["associates"]
    room = combo["room"]
    equipment = combo["equipment"]
    care_team = combo["care_team"]

    validate_appointment_allocation(
        center=center,
        assignment=assignment,
        modality=modality,
        start=start,
        end=end,
        associates=associates,
        room=room,
        equipment=equipment,
        customer_profile=customer_profile,
        exclude_appointment=exclude_appointment,
    )
    if not associates:
        raise ValidationError(ASSOCIATES_REQUIRED_FOR_BOOKING)
    return {
        "associates": associates,
        "room": room,
        "equipment": equipment,
        "care_team": care_team,
    }


def _subtract_appointment_from_busy_maps(busy_maps, appointment):
    exclusive_interval = (
        appointment.exclusive_start_datetime,
        appointment.exclusive_end_datetime,
    )
    updated = {
        "associate": dict(busy_maps["associate"]),
        "room": dict(busy_maps["room"]),
        "equipment": dict(busy_maps["equipment"]),
    }
    if appointment.room_id:
        room_key = str(appointment.room_id)
        updated["room"][room_key] = [
            item
            for item in updated["room"].get(room_key, [])
            if item != exclusive_interval
        ]
    if appointment.equipment_id:
        equipment_key = str(appointment.equipment_id)
        updated["equipment"][equipment_key] = [
            item
            for item in updated["equipment"].get(equipment_key, [])
            if item != exclusive_interval
        ]
    for link in appointment.associate_links.all():
        associate_key = str(link.associate_id)
        updated["associate"][associate_key] = [
            item
            for item in updated["associate"].get(associate_key, [])
            if item != exclusive_interval
        ]
    return updated
