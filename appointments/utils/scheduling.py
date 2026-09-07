from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.customers.models import CustomerCenterAssignment
from appointments.models import Appointment
from appointments.utils.calendar import (
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
    get_center_timezone_name,
)
from appointments.utils.care_teams import (
    expand_care_team_for_assignment,
    live_associate_center_assignments,
    live_care_teams_for_associate,
    load_active_center_care_team,
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


def busy_load_count(busy_map, resource_id):
    return len(busy_map.get(str(resource_id), []))


def booking_has_complete_pin(modality, associates, room):
    """Pin = associates list; in_person also requires room."""
    if not associates:
        return False
    if modality == AppointmentModes.IN_PERSON and room is None:
        return False
    return True


def assert_booking_pin_shape(modality, associates, room):
    """Reject partial pin (associates without room) so we never silently re-resolve."""
    if associates and modality == AppointmentModes.IN_PERSON and room is None:
        raise ValidationError(
            "Pin requires room_id for in-person appointments."
        )


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
        .prefetch_related("role_requirements__role")
        .select_related("required_room_type")
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
            associate__user__is_active=True,
            role__is_active=True,
        )
        .select_related("associate", "associate__user")
        .order_by("associate__created_at", "associate__pk")
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
    if modality == AppointmentModes.IN_PERSON:
        if assignment.required_room_type is not None:
            rooms = list(
                Room.objects.filter_active(
                    center=center,
                    room_type_ref=assignment.required_room_type,
                ).order_by("code", "pk")
            )
    return {
        "roles": role_pools,
        "rooms": rooms,
        "equipment": [],
    }


def validate_service_bookable(assignment, modality, resource_pools):
    """
    Config-level bookability. Virtual and in-person stay open here:
    zero-role virtual (preferred doctor) and preferred-room-only in-person
    are valid; find/resolve enforce room when needed.
    """
    if modality in (AppointmentModes.VIRTUAL, AppointmentModes.IN_PERSON):
        return
    role_pools = resource_pools["roles"]
    has_roles = len(role_pools) > 0
    has_room_type = assignment.required_room_type is not None
    if not has_roles and not has_room_type:
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
    for associate in resource_pools.get("extra_associates", []):
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


def first_active_equipment_for_room(room):
    return (
        Equipment.objects.filter(room=room, is_active=True, center=room.center)
        .order_by("created_at", "pk")
        .first()
    )


def resource_is_free(resource_type, resource_id, exclusive_start, exclusive_end, free_window_cache):
    windows = free_window_cache[resource_type].get(str(resource_id), [])
    return is_interval_contained_in_windows(
        exclusive_start, exclusive_end, windows
    )


def pick_associate_by_load(associates, associate_busy_map):
    return min(
        associates,
        key=lambda associate: (
            busy_load_count(associate_busy_map, associate.pk),
            associate.created_at,
            str(associate.pk),
        ),
    )


def pick_room_by_load(rooms, room_busy_map):
    return min(
        rooms,
        key=lambda room: (
            busy_load_count(room_busy_map, room.pk),
            room.code or "",
            str(room.pk),
        ),
    )


def get_live_assignment_for_associate(center, associate_id, modality):
    assignment = (
        live_associate_center_assignments(center, [associate_id])
        .select_related("associate", "associate__user", "role")
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
    for key in ("doctor_id", "health_coach_id"):
        value = preferred.get(key)
        if value:
            person_ids.append(str(value))
    return person_ids


def build_resolve_resource_pools(center, assignment, modality, preferred):
    preferred = preferred or {}
    resource_pools = build_service_resource_pools(center, assignment, modality)
    validate_service_bookable(assignment, modality, resource_pools)
    extra_associates = []
    care_team = None
    care_team_members = []

    care_team_id = preferred.get("care_team_id")
    if care_team_id:
        care_team_members = expand_care_team_for_assignment(
            center, care_team_id, assignment
        )
        if care_team_members:
            care_team = care_team_members[0].care_team
        for member in care_team_members:
            extra_associates.append(member.associate)
            for role_pool in resource_pools["roles"]:
                if role_pool["role_id"] == str(member.role.pk):
                    if member.associate not in role_pool["associates"]:
                        role_pool["associates"] = [
                            member.associate
                        ] + [
                            associate
                            for associate in role_pool["associates"]
                            if associate.pk != member.associate.pk
                        ]

    for person_id in collect_preferred_person_ids(preferred):
        center_assignment = get_live_assignment_for_associate(
            center, person_id, modality
        )
        associate = center_assignment.associate
        extra_associates.append(associate)
        matched_pool = False
        for role_pool in resource_pools["roles"]:
            preferred_id = preferred_associate_id_for_role(
                role_pool["role"], preferred
            )
            if preferred_id and str(preferred_id) == str(associate.pk):
                matched_pool = True
                if associate not in role_pool["associates"]:
                    if str(center_assignment.role.pk) != role_pool["role_id"]:
                        raise ValidationError(
                            "Preferred associate does not hold the required role."
                        )
                    role_pool["associates"] = [associate] + [
                        item
                        for item in role_pool["associates"]
                        if item.pk != associate.pk
                    ]
        if not matched_pool:
            # Prefer person outside service roles — still tracked as extra.
            pass

    preferred_id = preferred_room_id(preferred)
    if modality == AppointmentModes.IN_PERSON and preferred_id:
        preferred_room = (
            Room.objects.filter_active(center=center, pk=preferred_id).first()
        )
        if preferred_room is None:
            raise ValidationError("Preferred room is invalid or inactive.")
        resource_pools["rooms"] = [preferred_room]
    elif modality == AppointmentModes.IN_PERSON and not resource_pools["rooms"]:
        if assignment.required_room_type is None and not preferred_id:
            pass

    equipment_list = []
    for room in resource_pools["rooms"]:
        equipment = first_active_equipment_for_room(room)
        if equipment is not None:
            equipment_list.append(equipment)
    resource_pools["equipment"] = equipment_list
    resource_pools["extra_associates"] = extra_associates
    resource_pools["care_team"] = care_team
    resource_pools["care_team_members"] = care_team_members
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
    for associate in resource_pools.get("extra_associates", []):
        associate_key = str(associate.pk)
        if associate_key not in free_window_cache["associate"]:
            free_window_cache["associate"][associate_key] = (
                compute_associate_free_windows(
                    center,
                    associate,
                    query_start,
                    query_end,
                    timezone_name,
                    appointment_busy_map["associate"],
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

    filled_by_role = {}
    extras = []
    used_associate_ids = set()
    care_team = resource_pools.get("care_team")
    care_team_members = resource_pools.get("care_team_members") or []
    required_role_ids = {role_pool["role_id"] for role_pool in resource_pools["roles"]}

    for member in care_team_members:
        if not ensure_associate_free(
            member.associate,
            exclusive_start,
            exclusive_end,
            free_window_cache,
            soft=soft,
        ):
            return None
        role_id = str(member.role.pk)
        associate_id = str(member.associate.pk)
        if role_id in required_role_ids and role_id not in filled_by_role:
            filled_by_role[role_id] = member.associate
            used_associate_ids.add(associate_id)
        elif role_id not in required_role_ids:
            extras.append(
                {
                    "role_id": role_id,
                    "associate_id": member.associate.pk,
                }
            )
            used_associate_ids.add(associate_id)

    for person_id in collect_preferred_person_ids(preferred):
        if person_id in used_associate_ids:
            continue
        center_assignment = get_live_assignment_for_associate(
            center, person_id, modality
        )
        associate = center_assignment.associate
        if not ensure_associate_free(
            associate,
            exclusive_start,
            exclusive_end,
            free_window_cache,
            soft=soft,
        ):
            return None
        matched_role_id = None
        for role_pool in resource_pools["roles"]:
            preferred_id = preferred_associate_id_for_role(
                role_pool["role"], preferred
            )
            if preferred_id and str(preferred_id) == str(associate.pk):
                if str(center_assignment.role.pk) != role_pool["role_id"]:
                    if soft:
                        return None
                    raise ValidationError(
                        "Preferred associate does not hold the required role."
                    )
                matched_role_id = role_pool["role_id"]
                break
        if matched_role_id:
            if matched_role_id not in filled_by_role:
                filled_by_role[matched_role_id] = associate
            used_associate_ids.add(str(associate.pk))
        else:
            extras.append(
                {
                    "role_id": str(center_assignment.role.pk),
                    "associate_id": associate.pk,
                }
            )
            used_associate_ids.add(str(associate.pk))

    for role_pool in resource_pools["roles"]:
        role_id = role_pool["role_id"]
        if role_id in filled_by_role:
            continue
        free_associates = []
        for associate in role_pool["associates"]:
            if str(associate.pk) in used_associate_ids:
                continue
            if resource_is_free(
                "associate",
                associate.pk,
                exclusive_start,
                exclusive_end,
                free_window_cache,
            ):
                free_associates.append(associate)
        if not free_associates:
            if soft:
                return None
            raise ValidationError(
                f"No available associate for role {role_id}."
            )
        chosen = pick_associate_by_load(
            free_associates, appointment_busy_map["associate"]
        )
        filled_by_role[role_id] = chosen
        used_associate_ids.add(str(chosen.pk))

    room = None
    equipment = None
    if modality == AppointmentModes.IN_PERSON:
        preferred_id = preferred_room_id(preferred)
        free_rooms = []
        for candidate in resource_pools["rooms"]:
            if resource_is_free(
                "room",
                candidate.pk,
                exclusive_start,
                exclusive_end,
                free_window_cache,
            ):
                free_rooms.append(candidate)
        if preferred_id:
            preferred_room = next(
                (
                    candidate
                    for candidate in free_rooms
                    if str(candidate.pk) == str(preferred_id)
                ),
                None,
            )
            if preferred_room is None:
                if soft:
                    return None
                raise ValidationError("Selected room is not available.")
            room = preferred_room
        elif free_rooms:
            room = pick_room_by_load(free_rooms, appointment_busy_map["room"])
        else:
            if soft:
                return None
            raise ValidationError(
                "A room is required for in-person appointments."
            )

        equipment = first_active_equipment_for_room(room)
        if equipment is not None:
            if not resource_is_free(
                "equipment",
                equipment.pk,
                exclusive_start,
                exclusive_end,
                free_window_cache,
            ):
                if soft:
                    return None
                raise ValidationError("Selected equipment is not available.")
    else:
        if preferred_room_id(preferred):
            if soft:
                return None
            raise ValidationError(
                "Room and equipment must not be set for virtual appointments."
            )

    associates_payload = []
    for role_pool in resource_pools["roles"]:
        associate = filled_by_role[role_pool["role_id"]]
        associates_payload.append(
            {
                "role_id": role_pool["role_id"],
                "associate_id": associate.pk,
            }
        )
    associates_payload.extend(extras)
    return {
        "associates": associates_payload,
        "room": room,
        "equipment": equipment,
        "care_team": care_team,
    }


def serialize_pinned_slot(slot_start, slot_end, combo):
    room = combo["room"]
    equipment = combo["equipment"]
    return {
        "start": slot_start.isoformat(),
        "end": slot_end.isoformat(),
        "associates": [
            {
                "role_id": str(entry["role_id"]),
                "associate_id": str(entry["associate_id"]),
            }
            for entry in combo["associates"]
        ],
        "room_id": str(room.pk) if room is not None else None,
        "equipment_id": str(equipment.pk) if equipment is not None else None,
    }


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

    preferred = preferred or {}
    if (
        modality == AppointmentModes.IN_PERSON
        and assignment.required_room_type is None
        and not preferred_room_id(preferred)
    ):
        raise ValidationError(
            "A room is required for in-person appointments."
        )

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

    slots = []
    truncated = False
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
        slots.append(serialize_pinned_slot(slot_start, slot_end, combo))
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


def validate_associate_assignments(
    center, associates_payload, role_requirements, modality
):
    required_role_ids = {str(item.role.pk) for item in role_requirements}
    provided_role_ids = set()
    seen_associate_ids = set()
    for entry in associates_payload:
        role_id = str(entry["role_id"])
        associate_id = str(entry["associate_id"])
        if role_id in provided_role_ids:
            raise ValidationError("Duplicate role in associates pin.")
        if associate_id in seen_associate_ids:
            raise ValidationError("Duplicate associate in associates pin.")
        provided_role_ids.add(role_id)
        seen_associate_ids.add(associate_id)
        assignment = (
            live_associate_center_assignments(center, [entry["associate_id"]])
            .filter(role=role_id)
            .first()
        )
        if assignment is None:
            raise ValidationError(
                "Associate is not assigned to this center with the required role."
            )
        if not associate_modality_compatible(assignment.mode, modality):
            raise ValidationError("Associate modality is not compatible.")
    missing = required_role_ids - provided_role_ids
    if missing:
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
        validate_associate_assignments(
            center, associates, role_requirements, modality
        )

    resource_pools = build_service_resource_pools(center, assignment, modality)
    validate_service_bookable(assignment, modality, resource_pools)

    if modality == AppointmentModes.IN_PERSON:
        if room is None:
            raise ValidationError(
                "A room is required for in-person appointments."
            )
        if room.center.pk != center.pk:
            raise ValidationError("Room does not belong to this center.")
        if equipment is not None and equipment.center.pk != center.pk:
            raise ValidationError("Equipment does not belong to this center.")
        expected_equipment = first_active_equipment_for_room(room)
        if expected_equipment is None and equipment is not None:
            raise ValidationError("Equipment does not belong to the selected room.")
        if expected_equipment is not None:
            if equipment is None:
                raise ValidationError("Equipment is required for this room.")
            if equipment.pk != expected_equipment.pk:
                raise ValidationError(
                    "Equipment does not match the room's primary equipment."
                )
    else:
        if room is not None or equipment is not None:
            raise ValidationError(
                "Room and equipment must not be set for virtual appointments."
            )

    if associates:
        resource_pools["extra_associates"] = []
        for entry in associates:
            associate = Associate.objects.filter(pk=entry["associate_id"]).first()
            if associate is not None:
                resource_pools["extra_associates"].append(associate)
    if room is not None and room not in resource_pools["rooms"]:
        resource_pools["rooms"] = list(resource_pools["rooms"]) + [room]
    if equipment is not None:
        resource_pools["equipment"] = [equipment]

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

    for entry in associates or []:
        associate_key = str(entry["associate_id"])
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


def resolve_pinned_care_team(center, care_team_id, assignment, associates):
    """
    Stamp care_team on pin path only when every live team member appears in the pin.
    Extra pin rows (filled missing service roles) are allowed.
    """
    team = load_active_center_care_team(center, care_team_id)
    members = expand_care_team_for_assignment(center, care_team_id, assignment)
    pinned_pairs = {
        (str(entry["role_id"]), str(entry["associate_id"])) for entry in associates
    }
    for member in members:
        member_pair = (str(member.role.pk), str(member.associate.pk))
        if member_pair not in pinned_pairs:
            raise ValidationError(
                "Pinned associates do not match the preferred care team."
            )
    return team


def resolve_booking_combo(
    center,
    assignment,
    modality,
    preferred,
    start,
    end,
    associates=None,
    room=None,
    equipment=None,
    customer_profile=None,
    exclude_appointment=None,
):
    """
    Pin path: associates (+ room for in_person) provided → validate only.
    Else resolve from preferred, then validate.
    """
    preferred = preferred or {}
    associates = associates or []
    assert_booking_pin_shape(modality, associates, room)
    buffer_before = assignment.buffer_before
    buffer_after = assignment.buffer_after
    exclusive_start, exclusive_end = compute_exclusive_bounds(
        start, end, buffer_before, buffer_after
    )
    timezone_name = get_center_timezone_name(center)
    slot_date = start.astimezone(ZoneInfo(timezone_name)).date()

    has_pin = booking_has_complete_pin(modality, associates, room)

    care_team = None
    if not has_pin:
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
    else:
        care_team_id = preferred.get("care_team_id")
        if care_team_id:
            care_team = resolve_pinned_care_team(
                center, care_team_id, assignment, associates
            )

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
