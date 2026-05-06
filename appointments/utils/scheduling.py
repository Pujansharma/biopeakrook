from datetime import date, datetime, time, timedelta
from typing import Literal

from appointments.models import Appointment
from appointments.utils.intervals import (
    IST,
    Interval,
    expand_weekly_schedule,
    intersect_many,
    merge_intervals,
    subtract_intervals,
    split_into_slots,
)

type ResourceType = Literal["associate", "room", "equipment"]


def _expand_schedules_qs(qs, query_start: date, query_end: date) -> list[Interval]:
    """
    Expand a queryset of schedule objects (Schedule, RoomSchedule,
    EquipmentSchedule, or CenterOperatingHour) into concrete intervals.

    All these models share: day_of_week, start_time/open_time, end_time/close_time.
    """
    intervals: list[Interval] = []
    for s in qs:
        start_time = getattr(s, "start_time", None) or getattr(s, "open_time", None)
        end_time = getattr(s, "end_time", None) or getattr(s, "close_time", None)
        if start_time is None or end_time is None:
            continue
        intervals.extend(
            expand_weekly_schedule(
                day_of_week=s.day_of_week,
                start_time=start_time,
                end_time=end_time,
                query_start=query_start,
                query_end=query_end,
                valid_from=getattr(s, "valid_from", None),
                valid_until=getattr(s, "valid_until", None),
            )
        )
    return merge_intervals(intervals)


def _get_center_availability(
    center, query_start: date, query_end: date
) -> list[Interval]:
    """Expand center operating hours into available intervals."""
    qs = center.operating_hours.filter(is_open=True)
    return _expand_schedules_qs(qs, query_start, query_end)


def _get_associate_availability(
    associate,
    center,
    query_start: date,
    query_end: date,
) -> list[Interval]:
    """Expand associate schedules for a specific center."""
    qs = associate.schedules.filter(center=center)
    return _expand_schedules_qs(qs, query_start, query_end)


def _get_room_availability(room, query_start: date, query_end: date) -> list[Interval]:
    """Expand room operational schedules."""
    qs = room.schedules.filter(schedule_type="operational")
    return _expand_schedules_qs(qs, query_start, query_end)


def _get_equipment_availability(
    equipment,
    query_start: date,
    query_end: date,
) -> list[Interval]:
    """Expand equipment operational schedules."""
    qs = equipment.schedules.filter(schedule_type="operational")
    return _expand_schedules_qs(qs, query_start, query_end)


def _get_busy_intervals(
    associate,
    center,
    query_start: date,
    query_end: date,
    room=None,
    equipment=None,
) -> list[Interval]:
    """
    Collect all intervals that are unavailable within the query range:
    - Center holidays
    - Associate blocked periods
    - Existing non-cancelled appointments for the associate
    - Room maintenance windows (recurring)
    - Equipment bookings and maintenance (one-off)
    """
    busy: list[Interval] = []

    # Center holidays — full-day blocks
    for h in center.holidays.filter(date__range=(query_start, query_end)):
        busy.append(
            (
                datetime.combine(h.date, time.min, tzinfo=IST),
                datetime.combine(h.date, time.max, tzinfo=IST),
            )
        )

    # Associate blocked periods
    for b in associate.blocked_periods.filter(
        start_datetime__date__lte=query_end,
        end_datetime__date__gte=query_start,
    ):
        busy.append((b.start_datetime, b.end_datetime))

    # Existing appointments (exclude cancelled)
    for a in Appointment.objects.filter(
        associate=associate,
        start_datetime__date__lte=query_end,
        end_datetime__date__gte=query_start,
    ).exclude(status__in=["cancelled"]):
        busy.append((a.start_datetime, a.end_datetime))

    # Room maintenance schedules (recurring)
    if room is not None:
        for rs in room.schedules.filter(schedule_type="maintenance"):
            busy.extend(
                expand_weekly_schedule(
                    rs.day_of_week,
                    rs.start_time,
                    rs.end_time,
                    query_start,
                    query_end,
                )
            )

    # Equipment bookings and maintenance
    if equipment is not None:
        setup = timedelta(minutes=equipment.setup_time)
        cooldown = timedelta(minutes=equipment.cooldown_time)

        for eb in equipment.bookings.filter(
            start_datetime__date__lte=query_end,
            end_datetime__date__gte=query_start,
        ):
            busy.append((eb.start_datetime - setup, eb.end_datetime + cooldown))

        for m in equipment.maintenance_records.filter(
            scheduled_start__date__lte=query_end,
            scheduled_end__date__gte=query_start,
            status__in=["scheduled", "in_progress"],
        ):
            busy.append((m.scheduled_start, m.scheduled_end))

    busy.sort()
    return merge_intervals(busy)


def find_available_slots(
    associate,
    center,
    query_start: date,
    query_end: date,
    duration_minutes: int,
    buffer_minutes: int = 0,
    room=None,
    equipment=None,
) -> list[Interval]:
    """
    Find bookable time slots by intersecting resource availability
    and subtracting busy intervals.

    Available = Center ∩ Associate [∩ Room] [∩ Equipment]
                − Holidays − Blocks − Appointments − Maintenance

    Args:
        associate:        Associate model instance.
        center:           Center model instance.
        query_start:      Start date of the search window (inclusive).
        query_end:        End date of the search window (inclusive).
        duration_minutes: Length of each appointment slot in minutes.
        buffer_minutes:   Gap between consecutive slots in minutes.
        room:             Optional Room instance to include in intersection.
        equipment:        Optional Equipment instance to include in intersection.

    Returns:
        Sorted list of (start_datetime, end_datetime) tuples representing
        bookable slots in Asia/Kolkata timezone.
    """
    availability_layers = [
        _get_center_availability(center, query_start, query_end),
        _get_associate_availability(associate, center, query_start, query_end),
    ]

    if room is not None:
        availability_layers.append(
            _get_room_availability(room, query_start, query_end),
        )

    if equipment is not None:
        availability_layers.append(
            _get_equipment_availability(equipment, query_start, query_end),
        )

    available = intersect_many(*availability_layers)
    if not available:
        return []

    busy = _get_busy_intervals(
        associate,
        center,
        query_start,
        query_end,
        room,
        equipment,
    )

    available = subtract_intervals(available, busy)
    if not available:
        return []

    return split_into_slots(available, duration_minutes, buffer_minutes)


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------


def get_schedule_intervals(
    resource,
    resource_type: ResourceType,
    query_start: date,
    query_end: date,
    center=None,
) -> list[Interval]:
    """
    Get the raw recurring schedule intervals for a resource.

    Returns the time windows where this resource is *configured* to operate,
    before accounting for holidays, blocks, or existing bookings.

    Args:
        resource:      Associate, Room, or Equipment instance.
        resource_type: One of 'associate', 'room', 'equipment'.
        query_start:   Start date (inclusive).
        query_end:     End date (inclusive).
        center:        Required when resource_type is 'associate'.
    """
    match resource_type:
        case "associate":
            return _get_associate_availability(resource, center, query_start, query_end)
        case "room":
            return _get_room_availability(resource, query_start, query_end)
        case "equipment":
            return _get_equipment_availability(resource, query_start, query_end)


def get_blocked_periods(
    associate,
    center,
    query_start: date,
    query_end: date,
    room=None,
    equipment=None,
) -> list[Interval]:
    """
    Get all blocked/unavailable intervals within the query range.

    This is the union of:
    - Center holidays (full-day blocks)
    - Associate blocked periods (vacation, leave, etc.)
    - Room maintenance windows (recurring)
    - Equipment maintenance records (one-off)

    Does NOT include existing appointments — use get_scheduled_periods() for that.
    """
    blocked: list[Interval] = []

    for h in center.holidays.filter(date__range=(query_start, query_end)):
        blocked.append(
            (
                datetime.combine(h.date, time.min, tzinfo=IST),
                datetime.combine(h.date, time.max, tzinfo=IST),
            )
        )

    for b in associate.blocked_periods.filter(
        start_datetime__date__lte=query_end,
        end_datetime__date__gte=query_start,
    ):
        blocked.append((b.start_datetime, b.end_datetime))

    if room is not None:
        for rs in room.schedules.filter(schedule_type="maintenance"):
            blocked.extend(
                expand_weekly_schedule(
                    rs.day_of_week,
                    rs.start_time,
                    rs.end_time,
                    query_start,
                    query_end,
                )
            )

    if equipment is not None:
        for m in equipment.maintenance_records.filter(
            scheduled_start__date__lte=query_end,
            scheduled_end__date__gte=query_start,
            status__in=["scheduled", "in_progress"],
        ):
            blocked.append((m.scheduled_start, m.scheduled_end))

    blocked.sort()
    return merge_intervals(blocked)


def get_scheduled_periods(
    query_start: date,
    query_end: date,
    associate=None,
    room=None,
    equipment=None,
) -> list[Interval]:
    """
    Get intervals occupied by existing bookings within the query range.

    Returns non-cancelled appointment intervals for the associate, and/or
    equipment booking intervals (padded with setup/cooldown times).

    At least one of associate, room, equipment must be provided.
    """
    booked: list[Interval] = []

    if associate is not None:
        for a in Appointment.objects.filter(
            associate=associate,
            start_datetime__date__lte=query_end,
            end_datetime__date__gte=query_start,
        ).exclude(status__in=["cancelled"]):
            booked.append((a.start_datetime, a.end_datetime))

    if equipment is not None:
        setup = timedelta(minutes=equipment.setup_time)
        cooldown = timedelta(minutes=equipment.cooldown_time)
        for eb in equipment.bookings.filter(
            start_datetime__date__lte=query_end,
            end_datetime__date__gte=query_start,
        ):
            booked.append((eb.start_datetime - setup, eb.end_datetime + cooldown))

    booked.sort()
    return merge_intervals(booked)


def get_available_periods(
    associate,
    center,
    query_start: date,
    query_end: date,
    room=None,
    equipment=None,
) -> list[Interval]:
    """
    Get free time windows (continuous intervals, not slotted) where all
    specified resources are simultaneously available.

    Same logic as find_available_slots but without splitting into
    fixed-duration slots. Useful for calendar views showing free/busy blocks.

    Available = Center ∩ Associate [∩ Room] [∩ Equipment]
                − Holidays − Blocks − Appointments − Maintenance
    """
    availability_layers = [
        _get_center_availability(center, query_start, query_end),
        _get_associate_availability(associate, center, query_start, query_end),
    ]

    if room is not None:
        availability_layers.append(
            _get_room_availability(room, query_start, query_end),
        )

    if equipment is not None:
        availability_layers.append(
            _get_equipment_availability(equipment, query_start, query_end),
        )

    available = intersect_many(*availability_layers)
    if not available:
        return []

    busy = _get_busy_intervals(
        associate,
        center,
        query_start,
        query_end,
        room,
        equipment,
    )

    return subtract_intervals(available, busy)


def get_day_summary(
    associate,
    center,
    target_date: date,
    room=None,
    equipment=None,
) -> dict[str, list[Interval]]:
    """
    Get a complete breakdown of a single day for a resource combination.

    Returns:
        {
            'scheduled': [...],   # intervals with existing bookings
            'available': [...],   # free windows (bookable)
            'blocked':   [...],   # holidays, leave, maintenance
        }
    """
    return {
        "scheduled": get_scheduled_periods(
            target_date,
            target_date,
            associate=associate,
            equipment=equipment,
        ),
        "available": get_available_periods(
            associate,
            center,
            target_date,
            target_date,
            room=room,
            equipment=equipment,
        ),
        "blocked": get_blocked_periods(
            associate,
            center,
            target_date,
            target_date,
            room=room,
            equipment=equipment,
        ),
    }
