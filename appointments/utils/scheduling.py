from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.customers.models import CustomerCenterAssignment, CustomerProfile
from appointments.models import Appointment
from appointments.utils.calendar import (
    collect_associate_block_events,
    collect_associate_leave_events,
    collect_closure_events,
    collect_equipment_block_events,
    collect_equipment_downtime_events,
    collect_room_block_events,
    collect_room_downtime_events,
    expand_center_operating_hours,
    expand_roster_entries,
    get_center_timezone_name,
)
from appointments.utils.care_teams import (
    apply_care_team_to_resource_pools,
    expand_care_team_for_assignment,
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
            start_datetime__lt=range_end,
            end_datetime__gt=range_start,
        )
        .prefetch_related("associate_links")
        .select_related("room", "equipment")
    )
    associate_map = {}
    room_map = {}
    equipment_map = {}
    customer_map = {}
    for appointment in appointments:
        exclusive_interval = (
            appointment.exclusive_start_datetime,
            appointment.exclusive_end_datetime,
        )
        customer_key = str(appointment.customer_profile_id)
        customer_map.setdefault(customer_key, []).append(exclusive_interval)
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
        "customer": customer_map,
    }


def get_center_service_assignment(center, service):
    return (
        CenterServiceAssignment.objects.filter(
            center=center,
            service=service,
            is_active=True,
        )
        .prefetch_related("role_requirements__role")
        .select_related("required_room_type", "required_equipment_type")
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


def get_eligible_associates_for_role(center, role, modality):
    assignments = (
        AssociateCenterAssignment.objects.filter(
            center=center,
            role=role,
            is_active=True,
            associate__is_active=True,
        )
        .select_related("associate", "associate__user")
        .distinct()
    )
    associates = []
    for assignment in assignments:
        if associate_modality_compatible(assignment.mode, modality):
            associates.append(assignment.associate)
    return associates


def build_service_resource_pools(center, assignment, modality):
    role_requirements = assignment.role_requirements.filter(is_active=True)
    role_pools = []
    for requirement in role_requirements.select_related("role"):
        role = requirement.role
        role_pools.append(
            {
                "role_id": str(role.pk),
                "role": role,
                "associates": get_eligible_associates_for_role(
                    center, role, modality
                ),
            }
        )
    rooms = []
    equipment = []
    if modality == AppointmentModes.IN_PERSON:
        if assignment.required_room_type_id:
            rooms = list(
                Room.objects.filter_active(
                    center=center,
                    room_type=assignment.required_room_type,
                )
            )
        if assignment.required_equipment_type_id:
            equipment = list(
                Equipment.objects.filter_active(
                    center=center,
                    equipment_type=assignment.required_equipment_type,
                )
            )
    return {
        "roles": role_pools,
        "rooms": rooms,
        "equipment": equipment,
    }


def validate_service_bookable(assignment, modality, resource_pools):
    role_pools = resource_pools["roles"]
    has_roles = len(role_pools) > 0
    has_room_type = assignment.required_room_type_id is not None
    has_equipment_type = assignment.required_equipment_type_id is not None
    if not has_roles and modality == AppointmentModes.VIRTUAL:
        return
    if (
        not has_roles
        and modality == AppointmentModes.IN_PERSON
        and (has_room_type or has_equipment_type)
    ):
        return
    if not has_roles and not has_room_type and not has_equipment_type:
        raise ValidationError("Service is not bookable at this center.")


def compute_associate_free_windows(
    center,
    associate,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
):
    center_hours = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    roster_hours = expand_roster_entries(
        center, associate, query_start, query_end, timezone_name
    )
    base_intervals = intersect_intervals(center_hours, roster_hours)
    block_intervals, _ = collect_associate_block_events(
        center, associate, query_start, query_end, timezone_name
    )
    leave_intervals, _ = collect_associate_leave_events(
        center, associate, query_start, query_end, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    associate_busy = appointment_busy_map.get(str(associate.pk), [])
    busy_intervals = merge_intervals(
        block_intervals + leave_intervals + closure_intervals + associate_busy
    )
    return subtract_intervals(base_intervals, busy_intervals)


def compute_room_free_windows(
    center,
    room,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
):
    base_intervals = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    block_intervals, _ = collect_room_block_events(
        room, query_start, query_end, timezone_name
    )
    downtime_intervals, _ = collect_room_downtime_events(
        room, query_start, query_end, timezone_name
    )
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
):
    base_intervals = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    block_intervals, _ = collect_equipment_block_events(
        equipment, query_start, query_end, timezone_name
    )
    downtime_intervals, _ = collect_equipment_downtime_events(
        equipment, query_start, query_end, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    equipment_busy = appointment_busy_map.get(str(equipment.pk), [])
    busy_intervals = merge_intervals(
        block_intervals + downtime_intervals + closure_intervals + equipment_busy
    )
    return subtract_intervals(base_intervals, busy_intervals)


def build_resource_free_window_cache(
    center,
    resource_pools,
    query_start,
    query_end,
    timezone_name,
    appointment_busy_map,
):
    associate_windows = {}
    for role_pool in resource_pools["roles"]:
        for associate in role_pool["associates"]:
            associate_key = str(associate.pk)
            if associate_key not in associate_windows:
                associate_windows[associate_key] = compute_associate_free_windows(
                    center,
                    associate,
                    query_start,
                    query_end,
                    timezone_name,
                    appointment_busy_map["associate"],
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
        )
    return {
        "associate": associate_windows,
        "room": room_windows,
        "equipment": equipment_windows,
    }


def preferred_associate_id_for_role(role, preferred):
    if not preferred:
        return None
    role_key = str(role.pk)
    if role_key in preferred:
        return preferred[role_key]
    role_slug = f"{role.name.lower().replace(' ', '_')}_id"
    if role_slug in preferred:
        return preferred[role_slug]
    role_name_lower = role.name.lower()
    if "doctor" in role_name_lower and preferred.get("doctor_id"):
        return preferred["doctor_id"]
    if (
        ("health coach" in role_name_lower or "coach" in role_name_lower)
        and preferred.get("health_coach_id")
    ):
        return preferred["health_coach_id"]
    return None


def preferred_room_id(preferred):
    if not preferred:
        return None
    return preferred.get("room_id")


def filter_free_associates_for_role(
    role_pool,
    exclusive_start,
    exclusive_end,
    free_window_cache,
    preferred,
):
    available = []
    preferred_id = preferred_associate_id_for_role(role_pool["role"], preferred)
    for associate in role_pool["associates"]:
        associate_key = str(associate.pk)
        windows = free_window_cache["associate"].get(associate_key, [])
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, windows
        ):
            continue
        if preferred_id and str(associate.pk) != str(preferred_id):
            continue
        available.append(associate)
    if preferred_id and not available:
        return None
    return available


def filter_free_rooms(
    rooms,
    exclusive_start,
    exclusive_end,
    free_window_cache,
    preferred,
):
    available = []
    preferred_id = preferred_room_id(preferred)
    for room in rooms:
        room_key = str(room.pk)
        windows = free_window_cache["room"].get(room_key, [])
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, windows
        ):
            continue
        if preferred_id and str(room.pk) != str(preferred_id):
            continue
        available.append(room)
    if preferred_id and not available:
        return None
    return available


def filter_free_equipment(
    equipment_list,
    exclusive_start,
    exclusive_end,
    free_window_cache,
):
    available = []
    for equipment in equipment_list:
        equipment_key = str(equipment.pk)
        windows = free_window_cache["equipment"].get(equipment_key, [])
        if is_interval_contained_in_windows(
            exclusive_start, exclusive_end, windows
        ):
            available.append(equipment)
    return available


def serialize_associate_candidate(associate):
    return {
        "id": str(associate.pk),
        "name": get_associate_display_name(associate),
    }


def serialize_room_candidate(room):
    return {"id": str(room.pk), "name": room.name}


def serialize_equipment_candidate(equipment):
    return {"id": str(equipment.pk), "name": equipment.name}


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

    resource_pools = build_service_resource_pools(center, assignment, modality)
    validate_service_bookable(assignment, modality, resource_pools)
    preferred = preferred or {}
    care_team_id = preferred.get("care_team_id")
    if care_team_id:
        team_members = expand_care_team_for_assignment(
            center, care_team_id, assignment
        )
        apply_care_team_to_resource_pools(resource_pools, team_members)

    timezone_name = get_center_timezone_name(center)
    query_start = slot_date
    query_end = slot_date
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    busy_maps = load_busy_interval_maps(center, range_start, range_end)
    customer_busy = busy_maps["customer"].get(str(customer_profile.pk), [])

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

    slots = []
    truncated = False
    requires_room = (
        modality == AppointmentModes.IN_PERSON
        and assignment.required_room_type_id is not None
    )
    requires_equipment = (
        modality == AppointmentModes.IN_PERSON
        and assignment.required_equipment_type_id is not None
    )

    for slot_start, slot_end in candidate_slots:
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

        associates_by_role = {}
        slot_valid = True
        for role_pool in resource_pools["roles"]:
            role_candidates = filter_free_associates_for_role(
                role_pool,
                exclusive_start,
                exclusive_end,
                free_window_cache,
                preferred,
            )
            if role_candidates is None:
                slot_valid = False
                break
            if not role_candidates:
                slot_valid = False
                break
            associates_by_role[role_pool["role_id"]] = [
                serialize_associate_candidate(associate)
                for associate in role_candidates
            ]

        if not slot_valid:
            continue

        room_candidates = []
        if requires_room:
            free_rooms = filter_free_rooms(
                resource_pools["rooms"],
                exclusive_start,
                exclusive_end,
                free_window_cache,
                preferred,
            )
            if free_rooms is None or not free_rooms:
                continue
            room_candidates = [
                serialize_room_candidate(room) for room in free_rooms
            ]

        equipment_candidates = []
        if requires_equipment:
            free_equipment = filter_free_equipment(
                resource_pools["equipment"],
                exclusive_start,
                exclusive_end,
                free_window_cache,
            )
            if not free_equipment:
                continue
            equipment_candidates = [
                serialize_equipment_candidate(item) for item in free_equipment
            ]

        slot_payload = {
            "start": slot_start.isoformat(),
            "end": slot_end.isoformat(),
            "associates_by_role": associates_by_role,
        }
        if modality == AppointmentModes.IN_PERSON:
            if requires_room:
                slot_payload["rooms"] = room_candidates
            if requires_equipment:
                slot_payload["equipment"] = equipment_candidates
        slots.append(slot_payload)

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


def validate_associate_assignments(center, associates_payload, role_requirements):
    required_role_ids = {str(item.role_id) for item in role_requirements}
    provided_role_ids = set()
    for entry in associates_payload:
        role_id = str(entry["role_id"])
        associate_id = entry["associate_id"]
        provided_role_ids.add(role_id)
        if role_id not in required_role_ids:
            raise ValidationError(f"Unexpected role assignment: {role_id}.")
        assignment = AssociateCenterAssignment.objects.filter(
            center=center,
            associate_id=associate_id,
            role_id=role_id,
            is_active=True,
            associate__is_active=True,
        ).first()
        if assignment is None:
            raise ValidationError(
                "Associate is not assigned to this center with the required role."
            )
    if provided_role_ids != required_role_ids:
        raise ValidationError(
            "Exactly one associate is required for each service role."
        )


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

    role_requirements = list(
        assignment.role_requirements.filter(is_active=True).select_related("role")
    )
    if associates:
        validate_associate_assignments(center, associates, role_requirements)

    resource_pools = build_service_resource_pools(center, assignment, modality)
    validate_service_bookable(assignment, modality, resource_pools)

    if modality == AppointmentModes.IN_PERSON:
        if assignment.required_room_type_id and room is None:
            raise ValidationError("A room is required for this service.")
        if assignment.required_equipment_type_id and equipment is None:
            raise ValidationError("Equipment is required for this service.")
        if room is not None and room.center_id != center.pk:
            raise ValidationError("Room does not belong to this center.")
        if equipment is not None and equipment.center_id != center.pk:
            raise ValidationError("Equipment does not belong to this center.")
        if (
            room is not None
            and assignment.required_room_type_id
            and room.room_type_id != assignment.required_room_type_id
        ):
            raise ValidationError("Room type does not match service requirements.")
        if (
            equipment is not None
            and assignment.required_equipment_type_id
            and equipment.equipment_type_id != assignment.required_equipment_type_id
        ):
            raise ValidationError(
                "Equipment type does not match service requirements."
            )
    else:
        if room is not None or equipment is not None:
            raise ValidationError(
                "Room and equipment must not be set for virtual appointments."
            )

    buffer_before = assignment.buffer_before
    buffer_after = assignment.buffer_after
    exclusive_start, exclusive_end = compute_exclusive_bounds(
        start, end, buffer_before, buffer_after
    )

    timezone_name = get_center_timezone_name(center)
    slot_date = start.astimezone(ZoneInfo(timezone_name)).date()
    query_start = slot_date
    query_end = slot_date
    busy_maps = load_busy_interval_maps(center, exclusive_start, exclusive_end)
    if exclude_appointment is not None:
        busy_maps = _subtract_appointment_from_busy_maps(
            busy_maps, exclude_appointment
        )

    free_window_cache = build_resource_free_window_cache(
        center,
        resource_pools,
        query_start,
        query_end,
        timezone_name,
        busy_maps,
    )

    if customer_profile is not None:
        customer_busy = busy_maps["customer"].get(str(customer_profile.pk), [])
        if interval_overlaps_any(exclusive_start, exclusive_end, customer_busy):
            raise ValidationError(
                "Customer already has an appointment during this time."
            )

    for role_pool in resource_pools["roles"]:
        selected_associate = None
        for entry in associates or []:
            if str(entry["role_id"]) == role_pool["role_id"]:
                selected_associate = entry["associate_id"]
                break
        if selected_associate is None:
            raise ValidationError(
                f"Missing associate for role {role_pool['role_id']}."
            )
        associate_key = str(selected_associate)
        windows = free_window_cache["associate"].get(associate_key, [])
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, windows
        ):
            raise ValidationError("Selected associate is not available.")

    if room is not None:
        room_windows = free_window_cache["room"].get(str(room.pk), [])
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, room_windows
        ):
            raise ValidationError("Selected room is not available.")

    if equipment is not None:
        equipment_windows = free_window_cache["equipment"].get(
            str(equipment.pk), []
        )
        if not is_interval_contained_in_windows(
            exclusive_start, exclusive_end, equipment_windows
        ):
            raise ValidationError("Selected equipment is not available.")


def _subtract_appointment_from_busy_maps(busy_maps, appointment):
    exclusive_interval = (
        appointment.exclusive_start_datetime,
        appointment.exclusive_end_datetime,
    )
    customer_key = str(appointment.customer_profile_id)
    updated = {
        "associate": dict(busy_maps["associate"]),
        "room": dict(busy_maps["room"]),
        "equipment": dict(busy_maps["equipment"]),
        "customer": dict(busy_maps["customer"]),
    }
    updated["customer"][customer_key] = [
        item
        for item in updated["customer"].get(customer_key, [])
        if item != exclusive_interval
    ]
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
