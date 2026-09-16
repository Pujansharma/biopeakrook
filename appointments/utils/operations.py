import calendar
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from appointments.models import Appointment, AppointmentAssociate
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
from appointments.utils.care_teams import live_care_teams_for_associate
from appointments.utils.constants import (
    AvailabilityGranularity,
    BUSY_APPOINTMENT_STATUSES,
)
from appointments.utils.intervals import (
    datetime_range_for_dates,
    intersect_intervals,
    merge_intervals,
    resolve_query_date_range,
    subtract_intervals,
)
from appointments.utils.metrics import record_operations_cache_hit
from inventory.models import Equipment, Room

OPERATIONS_CACHE_TTL = 600
OPERATIONS_VERSION_KEY = "appointments:ops:version:{center_id}"
STAFF_IDLE_UTILIZATION_THRESHOLD = 0.2
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INVALID_GRANULARITY_MESSAGE = "Invalid granularity. Use day, week, or month."
END_BEFORE_START_MESSAGE = "End date cannot be before start date."


def operations_cache_version_key(center_id) -> str:
    return OPERATIONS_VERSION_KEY.format(center_id=center_id)


def operations_cache_key(center_id, start_date, end_date, tab) -> str:
    version = cache.get(operations_cache_version_key(center_id), 1)
    return (
        f"appointments:ops:{center_id}:v{version}:"
        f"{start_date.isoformat()}:{end_date.isoformat()}:{tab}"
    )


def invalidate_operations_cache(center_id) -> None:
    version_key = operations_cache_version_key(center_id)
    current_version = cache.get(version_key, 1)
    cache.set(version_key, current_version + 1, timeout=None)


def get_cached_operations(center, start_date, end_date, tab, builder):
    cache_key = operations_cache_key(center.pk, start_date, end_date, tab)
    cached = cache.get(cache_key)
    if cached is not None:
        record_operations_cache_hit(center.pk, tab, True)
        return cached
    record_operations_cache_hit(center.pk, tab, False)
    payload = builder(center, start_date, end_date)
    cache.set(cache_key, payload, timeout=OPERATIONS_CACHE_TTL)
    return payload


def parse_operations_iso_date(raw, field_name):
    if not ISO_DATE_PATTERN.fullmatch(raw):
        raise DjangoValidationError(f"Invalid {field_name}. Use YYYY-MM-DD.")
    year, month, day = (int(part) for part in raw.split("-"))
    if month < 1 or month > 12:
        raise DjangoValidationError(f"Invalid {field_name}. Use YYYY-MM-DD.")
    max_day = calendar.monthrange(year, month)[1]
    if day < 1 or day > max_day:
        raise DjangoValidationError(f"Invalid {field_name}. Use YYYY-MM-DD.")
    return date(year, month, day)


def parse_operations_date_range(query_params, default_start: date | None = None):
    start_raw = query_params.get("start")
    end_raw = query_params.get("end")
    granularity = query_params.get("granularity", AvailabilityGranularity.WEEK)
    if default_start is None:
        default_start = timezone_today()
    start_date = (
        parse_operations_iso_date(start_raw, "start date")
        if start_raw
        else default_start
    )
    if end_raw:
        end_date = parse_operations_iso_date(end_raw, "end date")
        if end_date < start_date:
            raise DjangoValidationError(END_BEFORE_START_MESSAGE)
        return start_date, end_date
    if granularity not in AvailabilityGranularity.values:
        raise DjangoValidationError(INVALID_GRANULARITY_MESSAGE)
    return resolve_query_date_range(start_date, granularity)


def timezone_today() -> date:
    return datetime.now(tz=ZoneInfo("UTC")).date()


def interval_total_minutes(intervals) -> float:
    total_seconds = 0.0
    for interval_start, interval_end in intervals:
        total_seconds += (interval_end - interval_start).total_seconds()
    return total_seconds / 60.0


def minutes_to_hours(minutes: float) -> float:
    return round(minutes / 60.0, 2)


def appointment_range_filter(center, range_start, range_end):
    return Appointment.objects.filter(
        center=center,
        status__in=BUSY_APPOINTMENT_STATUSES,
        start_datetime__lt=range_end,
        end_datetime__gt=range_start,
    )


def aggregate_booked_metrics(center, start_date, end_date):
    timezone_name = get_center_timezone_name(center)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )
    queryset = appointment_range_filter(center, range_start, range_end)
    totals = queryset.aggregate(
        appointment_count=Count("pk"),
        booked_minutes=Sum("duration_minutes"),
    )
    status_breakdown = {
        row["status"]: row["count"]
        for row in queryset.values("status").annotate(count=Count("pk"))
    }
    service_breakdown = [
        {
            "service_id": str(row["service_id"]),
            "service_name": row["service__name"],
            "booked_minutes": row["booked_minutes"] or 0,
            "appointment_count": row["appointment_count"],
        }
        for row in queryset.values("service_id", "service__name").annotate(
            booked_minutes=Sum("duration_minutes"),
            appointment_count=Count("pk"),
        )
    ]
    return {
        "appointment_count": totals["appointment_count"] or 0,
        "booked_minutes": totals["booked_minutes"] or 0,
        "booked_hours": minutes_to_hours(totals["booked_minutes"] or 0),
        "status_breakdown": status_breakdown,
        "service_breakdown": service_breakdown,
    }


def build_peak_histogram(center, start_date, end_date):
    timezone_name = get_center_timezone_name(center)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )
    local_tz = ZoneInfo(timezone_name)
    histogram = {hour: 0 for hour in range(24)}
    appointments = appointment_range_filter(center, range_start, range_end)
    for appointment in appointments.only("start_datetime"):
        local_hour = appointment.start_datetime.astimezone(local_tz).hour
        histogram[local_hour] += 1
    return [
        {"hour": hour, "appointment_count": histogram[hour]}
        for hour in range(24)
        if histogram[hour] > 0
    ]


def build_associate_capacity(center, associate, start_date, end_date):
    timezone_name = get_center_timezone_name(center)
    center_hours = expand_center_operating_hours(
        center, start_date, end_date, timezone_name
    )
    roster_hours = expand_roster_entries(
        center, associate, start_date, end_date, timezone_name
    )
    base_intervals = intersect_intervals(center_hours, roster_hours)
    block_intervals, _ = collect_associate_block_events(
        center, associate, start_date, end_date, timezone_name
    )
    leave_intervals, _ = collect_associate_leave_events(
        center, associate, start_date, end_date, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, start_date, end_date, timezone_name
    )
    care_teams = live_care_teams_for_associate(center, associate)
    team_block_intervals, _ = collect_care_team_block_events(
        center, care_teams, start_date, end_date, timezone_name
    )
    busy_intervals = merge_intervals(
        block_intervals + leave_intervals + closure_intervals + team_block_intervals
    )
    available_intervals = subtract_intervals(base_intervals, busy_intervals)
    available_minutes = interval_total_minutes(available_intervals)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )
    booked_minutes = (
        AppointmentAssociate.objects.filter(
            associate=associate,
            appointment__center=center,
            appointment__status__in=BUSY_APPOINTMENT_STATUSES,
            appointment__start_datetime__lt=range_end,
            appointment__end_datetime__gt=range_start,
        )
        .aggregate(total=Sum("appointment__duration_minutes"))
        .get("total")
        or 0
    )
    utilization = 0.0
    if available_minutes > 0:
        utilization = round(booked_minutes / available_minutes, 4)
    user = associate.user
    name = " ".join(
        part for part in [user.first_name or "", user.last_name or ""] if part
    ).strip()
    return {
        "associate_id": str(associate.pk),
        "name": name or str(associate.pk),
        "available_minutes": round(available_minutes, 2),
        "available_hours": minutes_to_hours(available_minutes),
        "booked_minutes": booked_minutes,
        "booked_hours": minutes_to_hours(booked_minutes),
        "utilization": utilization,
    }


def build_room_capacity(center, room, start_date, end_date):
    timezone_name = get_center_timezone_name(center)
    base_intervals = expand_center_operating_hours(
        center, start_date, end_date, timezone_name
    )
    block_intervals, _ = collect_room_block_events(
        room, start_date, end_date, timezone_name
    )
    downtime_intervals, _ = collect_room_downtime_events(
        room, start_date, end_date, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, start_date, end_date, timezone_name
    )
    busy_intervals = merge_intervals(
        block_intervals + downtime_intervals + closure_intervals
    )
    available_intervals = subtract_intervals(base_intervals, busy_intervals)
    available_minutes = interval_total_minutes(available_intervals)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )
    booked_minutes = (
        Appointment.objects.filter(
            center=center,
            room=room,
            status__in=BUSY_APPOINTMENT_STATUSES,
            start_datetime__lt=range_end,
            end_datetime__gt=range_start,
        )
        .aggregate(total=Sum("duration_minutes"))
        .get("total")
        or 0
    )
    utilization = 0.0
    if available_minutes > 0:
        utilization = round(booked_minutes / available_minutes, 4)
    return {
        "room_id": str(room.pk),
        "name": room.name,
        "available_minutes": round(available_minutes, 2),
        "available_hours": minutes_to_hours(available_minutes),
        "booked_minutes": booked_minutes,
        "booked_hours": minutes_to_hours(booked_minutes),
        "utilization": utilization,
    }


def build_equipment_capacity(center, equipment, start_date, end_date):
    timezone_name = get_center_timezone_name(center)
    base_intervals = expand_center_operating_hours(
        center, start_date, end_date, timezone_name
    )
    block_intervals, _ = collect_equipment_block_events(
        equipment, start_date, end_date, timezone_name
    )
    downtime_intervals, _ = collect_equipment_downtime_events(
        equipment, start_date, end_date, timezone_name
    )
    closure_intervals, _ = collect_closure_events(
        center, start_date, end_date, timezone_name
    )
    busy_intervals = merge_intervals(
        block_intervals + downtime_intervals + closure_intervals
    )
    available_intervals = subtract_intervals(base_intervals, busy_intervals)
    available_minutes = interval_total_minutes(available_intervals)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )
    booked_minutes = (
        Appointment.objects.filter(
            center=center,
            equipment=equipment,
            status__in=BUSY_APPOINTMENT_STATUSES,
            start_datetime__lt=range_end,
            end_datetime__gt=range_start,
        )
        .aggregate(total=Sum("duration_minutes"))
        .get("total")
        or 0
    )
    utilization = 0.0
    if available_minutes > 0:
        utilization = round(booked_minutes / available_minutes, 4)
    return {
        "equipment_id": str(equipment.pk),
        "name": equipment.name,
        "available_minutes": round(available_minutes, 2),
        "available_hours": minutes_to_hours(available_minutes),
        "booked_minutes": booked_minutes,
        "booked_hours": minutes_to_hours(booked_minutes),
        "utilization": utilization,
    }


def build_operations_overview(center, start_date, end_date) -> dict:
    booked = aggregate_booked_metrics(center, start_date, end_date)
    return {
        "center_id": str(center.pk),
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "appointment_count": booked["appointment_count"],
        "booked_minutes": booked["booked_minutes"],
        "booked_hours": booked["booked_hours"],
        "status_breakdown": booked["status_breakdown"],
        "service_breakdown": booked["service_breakdown"],
        "peak_hours": build_peak_histogram(center, start_date, end_date),
    }


def build_operations_staff(center, start_date, end_date) -> list:
    associate_ids = AssociateCenterAssignment.objects.filter(
        center=center,
        is_active=True,
        associate__user__is_active=True,
    ).values_list("associate_id", flat=True)
    associates = Associate.objects.filter(pk__in=associate_ids, is_active=True)
    return [
        build_associate_capacity(center, associate, start_date, end_date)
        for associate in associates
    ]


def build_operations_rooms(center, start_date, end_date) -> list:
    rooms = Room.objects.filter(center=center, is_active=True)
    return [
        build_room_capacity(center, room, start_date, end_date)
        for room in rooms
    ]


def build_operations_equipment(center, start_date, end_date) -> list:
    equipment_items = Equipment.objects.filter(center=center, is_active=True)
    return [
        build_equipment_capacity(center, item, start_date, end_date)
        for item in equipment_items
    ]


def build_operations_bottlenecks(center, start_date, end_date) -> list:
    bottlenecks = []
    timezone_name = get_center_timezone_name(center)
    range_start, range_end = datetime_range_for_dates(
        start_date, end_date, timezone_name
    )

    rooms = Room.objects.filter(center=center, is_active=True)
    for room in rooms:
        _, downtime_events = collect_room_downtime_events(
            room, start_date, end_date, timezone_name
        )
        for event in downtime_events:
            event_start = datetime.fromisoformat(event["start"])
            event_end = datetime.fromisoformat(event["end"])
            dependent_count = Appointment.objects.filter(
                center=center,
                room=room,
                status__in=BUSY_APPOINTMENT_STATUSES,
                start_datetime__lt=event_end,
                end_datetime__gt=event_start,
            ).count()
            if dependent_count > 0:
                bottlenecks.append(
                    {
                        "type": "room_downtime",
                        "resource_id": str(room.pk),
                        "resource_name": room.name,
                        "start": event["start"],
                        "end": event["end"],
                        "dependent_appointment_count": dependent_count,
                        "reason": event.get("reason", ""),
                    }
                )

    equipment_items = Equipment.objects.filter(center=center, is_active=True)
    for equipment in equipment_items:
        _, downtime_events = collect_equipment_downtime_events(
            equipment, start_date, end_date, timezone_name
        )
        for event in downtime_events:
            event_start = datetime.fromisoformat(event["start"])
            event_end = datetime.fromisoformat(event["end"])
            dependent_count = Appointment.objects.filter(
                center=center,
                equipment=equipment,
                status__in=BUSY_APPOINTMENT_STATUSES,
                start_datetime__lt=event_end,
                end_datetime__gt=event_start,
            ).count()
            if dependent_count > 0:
                bottlenecks.append(
                    {
                        "type": "equipment_downtime",
                        "resource_id": str(equipment.pk),
                        "resource_name": equipment.name,
                        "start": event["start"],
                        "end": event["end"],
                        "dependent_appointment_count": dependent_count,
                        "reason": event.get("reason", ""),
                    }
                )

    staff_rows = build_operations_staff(center, start_date, end_date)
    for staff_row in staff_rows:
        if (
            staff_row["available_minutes"] > 0
            and staff_row["utilization"] < STAFF_IDLE_UTILIZATION_THRESHOLD
        ):
            bottlenecks.append(
                {
                    "type": "staff_underutilized",
                    "resource_id": staff_row["associate_id"],
                    "resource_name": staff_row["name"],
                    "utilization": staff_row["utilization"],
                    "available_hours": staff_row["available_hours"],
                    "booked_hours": staff_row["booked_hours"],
                }
            )

    return bottlenecks


def summarize_operations_capacity(rows, resource_type):
    available_minutes = sum(row["available_minutes"] for row in rows)
    booked_minutes = sum(row["booked_minutes"] for row in rows)
    utilization = 0.0
    if available_minutes > 0:
        utilization = round(booked_minutes / available_minutes, 4)
    return {
        "resource_type": resource_type,
        "resource_count": len(rows),
        "available_minutes": round(available_minutes, 2),
        "available_hours": minutes_to_hours(available_minutes),
        "booked_minutes": booked_minutes,
        "booked_hours": minutes_to_hours(booked_minutes),
        "utilization": utilization,
    }


def build_operations_capacity(center, start_date, end_date) -> dict:
    staff_rows = build_operations_staff(center, start_date, end_date)
    room_rows = build_operations_rooms(center, start_date, end_date)
    equipment_rows = build_operations_equipment(center, start_date, end_date)
    return {
        "center_id": str(center.pk),
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "staff": summarize_operations_capacity(staff_rows, "staff"),
        "rooms": summarize_operations_capacity(room_rows, "rooms"),
        "equipment": summarize_operations_capacity(equipment_rows, "equipment"),
    }
