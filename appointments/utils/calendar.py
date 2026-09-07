from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.centers.models import CenterClosure, CenterOperatingHour
from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    AssociateRosterEntry,
    Appointment,
    CareTeamAvailabilityBlock,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.utils.care_teams import (
    live_associates_for_care_team,
    live_care_teams_for_associate,
)
from appointments.utils.constants import BUSY_APPOINTMENT_STATUSES
from appointments.utils.constants import LeaveScope
from appointments.utils.intervals import (
    clip_intervals_to_range,
    datetime_range_for_dates,
    expand_weekly_time_windows,
    full_day_interval,
    intersect_intervals,
    merge_intervals,
    resolve_query_date_range,
    subtract_intervals,
)
from appointments.utils.overlap import local_day_window
from core.utils.constants import AppointmentDays


def get_center_timezone_name(center):
    # ponytail: Center has no timezone field yet; use project default.
    del center
    return settings.TIME_ZONE


def recurring_block_in_query_range(query_start, query_end):
    """Recurring rows that can expand into [query_start, query_end]."""
    started = models.Q(effective_from__isnull=True) | models.Q(
        effective_from__lte=query_end
    )
    not_ended = models.Q(effective_until__isnull=True) | models.Q(
        effective_until__gte=query_start
    )
    return models.Q(is_recurring=True) & started & not_ended


def one_off_datetime_overlap(range_start, range_end):
    """Overlap: start < range_end and end > range_start."""
    return models.Q(
        is_recurring=False,
        start_datetime__isnull=False,
        end_datetime__isnull=False,
        start_datetime__lt=range_end,
        end_datetime__gt=range_start,
    )


def one_off_local_date_in_range(query_start, query_end):
    return models.Q(
        is_recurring=False,
        date__isnull=False,
        date__gte=query_start,
        date__lte=query_end,
    )


def datetime_window_overlap(range_start, range_end):
    return models.Q(
        start_datetime__lt=range_end,
        end_datetime__gt=range_start,
    )


def serialize_interval(interval):
    interval_start, interval_end = interval
    return {
        "start": interval_start.isoformat(),
        "end": interval_end.isoformat(),
    }


def serialize_event(event_type, event_id, interval, extra=None):
    payload = {
        "type": event_type,
        "id": str(event_id),
        "start": interval[0].isoformat(),
        "end": interval[1].isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def iter_dates_in_range(query_start, query_end):
    current = query_start
    while current <= query_end:
        yield current
        current += timedelta(days=1)


def expand_center_operating_hours(center, query_start, query_end, timezone_name):
    operating_hours = CenterOperatingHour.objects.filter(
        center=center, is_active=True, is_open=True
    )
    intervals = []
    for operating_hour in operating_hours:
        if operating_hour.open_time is None or operating_hour.close_time is None:
            continue
        intervals.extend(
            expand_weekly_time_windows(
                query_start,
                query_end,
                operating_hour.day_of_week,
                operating_hour.open_time,
                operating_hour.close_time,
                timezone_name,
            )
        )
    return merge_intervals(intervals)


def expand_roster_entries(center, associate, query_start, query_end, timezone_name):
    roster_entries = AssociateRosterEntry.objects.filter(
        center=center,
        associate=associate,
        is_active=True,
    )
    intervals = []
    for roster_entry in roster_entries:
        intervals.extend(
            expand_weekly_time_windows(
                query_start,
                query_end,
                roster_entry.day_of_week,
                roster_entry.start_time,
                roster_entry.end_time,
                timezone_name,
            )
        )
    return merge_intervals(intervals)


def expand_recurring_block(block, query_start, query_end, timezone_name):
    return expand_weekly_time_windows(
        query_start,
        query_end,
        block.day_of_week,
        block.recurring_start_time,
        block.recurring_end_time,
        timezone_name,
        effective_from=block.effective_from,
        effective_until=block.effective_until,
    )


def collect_associate_block_events(center, associate, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    blocks = AssociateAvailabilityBlock.objects.filter(
        center=center,
        associate=associate,
        is_active=True,
    ).filter(
        recurring_block_in_query_range(query_start, query_end)
        | one_off_datetime_overlap(range_start, range_end)
    )
    intervals = []
    events = []
    for block in blocks:
        if block.is_recurring:
            block_intervals = expand_recurring_block(
                block, query_start, query_end, timezone_name
            )
            for block_interval in block_intervals:
                events.append(
                    serialize_event(
                        "associate_block_recurring",
                        block.pk,
                        block_interval,
                        {"reason": block.reason, "is_recurring": True},
                    )
                )
            intervals.extend(block_intervals)
        elif block.start_datetime and block.end_datetime:
            block_interval = (block.start_datetime, block.end_datetime)
            clipped = clip_intervals_to_range([block_interval], range_start, range_end)
            intervals.extend(clipped)
            for clipped_interval in clipped:
                events.append(
                    serialize_event(
                        "associate_block",
                        block.pk,
                        clipped_interval,
                        {"reason": block.reason, "is_recurring": False},
                    )
                )
    return merge_intervals(intervals), events


def collect_associate_leave_events(center, associate, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    leaves = (
        AssociateLeave.objects.filter(
            associate=associate,
            is_active=True,
        )
        .filter(
            models.Q(scope=LeaveScope.ALL_CENTERS)
            | models.Q(scope=LeaveScope.CENTER, center=center)
        )
        .filter(datetime_window_overlap(range_start, range_end))
    )
    intervals = []
    events = []
    for leave in leaves:
        leave_interval = (leave.start_datetime, leave.end_datetime)
        clipped = clip_intervals_to_range([leave_interval], range_start, range_end)
        intervals.extend(clipped)
        for clipped_interval in clipped:
            events.append(
                serialize_event(
                    "associate_leave",
                    leave.pk,
                    clipped_interval,
                    {
                        "reason": leave.reason,
                        "scope": leave.scope,
                        "center_id": str(leave.center.pk) if leave.center else None,
                    },
                )
            )
    return merge_intervals(intervals), events


def events_with_associate_id(events, associate):
    annotated = []
    for event in events:
        payload = dict(event)
        payload["associate_id"] = str(associate.pk)
        annotated.append(payload)
    return annotated


def collect_care_team_block_events(
    center, care_teams, query_start, query_end, timezone_name
):
    if not care_teams:
        return [], []
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    care_team_ids = [care_team.pk for care_team in care_teams]
    blocks = CareTeamAvailabilityBlock.objects.filter(
        center=center,
        care_team_id__in=care_team_ids,
        is_active=True,
    ).filter(
        recurring_block_in_query_range(query_start, query_end)
        | one_off_datetime_overlap(range_start, range_end)
    ).select_related("care_team")
    intervals = []
    events = []
    for block in blocks:
        extra = {
            "reason": block.reason,
            "is_recurring": block.is_recurring,
            "care_team_id": str(block.care_team_id),
            "care_team_name": block.care_team.name,
        }
        if block.is_recurring:
            block_intervals = expand_recurring_block(
                block, query_start, query_end, timezone_name
            )
            event_type = "care_team_block_recurring"
            extra["is_recurring"] = True
            for block_interval in block_intervals:
                events.append(
                    serialize_event(event_type, block.pk, block_interval, extra)
                )
            intervals.extend(block_intervals)
        elif block.start_datetime and block.end_datetime:
            block_interval = (block.start_datetime, block.end_datetime)
            clipped = clip_intervals_to_range([block_interval], range_start, range_end)
            intervals.extend(clipped)
            extra["is_recurring"] = False
            for clipped_interval in clipped:
                events.append(
                    serialize_event(
                        "care_team_block", block.pk, clipped_interval, extra
                    )
                )
    return merge_intervals(intervals), events


def collect_room_block_events(room, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    blocks = RoomAvailabilityBlock.objects.filter(room=room, is_active=True).filter(
        recurring_block_in_query_range(query_start, query_end)
        | one_off_local_date_in_range(query_start, query_end)
    )
    intervals = []
    events = []
    for block in blocks:
        if block.is_recurring:
            block_intervals = expand_recurring_block(
                block, query_start, query_end, timezone_name
            )
            for block_interval in block_intervals:
                events.append(
                    serialize_event(
                        "room_block_recurring",
                        block.pk,
                        block_interval,
                        {"reason": block.reason, "is_recurring": True},
                    )
                )
            intervals.extend(block_intervals)
        elif block.date and block.start_time and block.end_time:
            block_interval = local_day_window(
                block.date, block.start_time, block.end_time, timezone_name
            )
            clipped = clip_intervals_to_range([block_interval], range_start, range_end)
            intervals.extend(clipped)
            for clipped_interval in clipped:
                events.append(
                    serialize_event(
                        "room_block",
                        block.pk,
                        clipped_interval,
                        {"reason": block.reason, "is_recurring": False},
                    )
                )
    return merge_intervals(intervals), events


def collect_room_downtime_events(room, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    downtimes = RoomDowntime.objects.filter(
        room=room,
        is_active=True,
        date__gte=query_start,
        date__lte=query_end,
    )
    intervals = []
    events = []
    for downtime in downtimes:
        downtime_interval = local_day_window(
            downtime.date, downtime.start_time, downtime.end_time, timezone_name
        )
        clipped = clip_intervals_to_range([downtime_interval], range_start, range_end)
        intervals.extend(clipped)
        for clipped_interval in clipped:
            events.append(
                serialize_event(
                    "room_downtime",
                    downtime.pk,
                    clipped_interval,
                    {"reason": downtime.reason},
                )
            )
    return merge_intervals(intervals), events


def collect_equipment_block_events(equipment, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    blocks = EquipmentAvailabilityBlock.objects.filter(
        equipment=equipment, is_active=True
    ).filter(
        recurring_block_in_query_range(query_start, query_end)
        | one_off_local_date_in_range(query_start, query_end)
    )
    intervals = []
    events = []
    for block in blocks:
        if block.is_recurring:
            block_intervals = expand_recurring_block(
                block, query_start, query_end, timezone_name
            )
            for block_interval in block_intervals:
                events.append(
                    serialize_event(
                        "equipment_block_recurring",
                        block.pk,
                        block_interval,
                        {"reason": block.reason, "is_recurring": True},
                    )
                )
            intervals.extend(block_intervals)
        elif block.date and block.start_time and block.end_time:
            block_interval = local_day_window(
                block.date, block.start_time, block.end_time, timezone_name
            )
            clipped = clip_intervals_to_range([block_interval], range_start, range_end)
            intervals.extend(clipped)
            for clipped_interval in clipped:
                events.append(
                    serialize_event(
                        "equipment_block",
                        block.pk,
                        clipped_interval,
                        {"reason": block.reason, "is_recurring": False},
                    )
                )
    return merge_intervals(intervals), events


def collect_equipment_downtime_events(equipment, query_start, query_end, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    downtimes = EquipmentDowntime.objects.filter(
        equipment=equipment,
        is_active=True,
        date__gte=query_start,
        date__lte=query_end,
    )
    intervals = []
    events = []
    for downtime in downtimes:
        downtime_interval = local_day_window(
            downtime.date, downtime.start_time, downtime.end_time, timezone_name
        )
        clipped = clip_intervals_to_range([downtime_interval], range_start, range_end)
        intervals.extend(clipped)
        for clipped_interval in clipped:
            events.append(
                serialize_event(
                    "equipment_downtime",
                    downtime.pk,
                    clipped_interval,
                    {"reason": downtime.reason},
                )
            )
    return merge_intervals(intervals), events


def collect_closure_events(center, query_start, query_end, timezone_name):
    closures = CenterClosure.objects.filter(
        center=center,
        is_active=True,
        date__gte=query_start,
        date__lte=query_end,
    )
    intervals = []
    events = []
    for closure in closures:
        closure_interval = full_day_interval(closure.date, timezone_name)
        intervals.append(closure_interval)
        events.append(
            serialize_event(
                "closure",
                closure.pk,
                closure_interval,
                {
                    "closure_type": closure.type,
                    "reason": closure.reason,
                },
            )
        )
    return merge_intervals(intervals), events


def filter_events_for_day(events, day_value, timezone_name):
    range_start, range_end = datetime_range_for_dates(
        day_value, day_value, timezone_name
    )
    filtered = []
    for event in events:
        event_start = datetime.fromisoformat(event["start"])
        event_end = datetime.fromisoformat(event["end"])
        if event_start <= range_end and event_end >= range_start:
            filtered.append(event)
    return filtered


def build_day_payload(
    day_value,
    base_intervals,
    available_intervals,
    events,
    timezone_name,
):
    range_start, range_end = datetime_range_for_dates(
        day_value, day_value, timezone_name
    )
    day_base = clip_intervals_to_range(base_intervals, range_start, range_end)
    day_available = clip_intervals_to_range(available_intervals, range_start, range_end)
    day_events = filter_events_for_day(events, day_value, timezone_name)
    day_of_week = str(day_value.weekday())
    return {
        "date": day_value.isoformat(),
        "day_of_week": day_of_week,
        "day_of_week_name": AppointmentDays(day_of_week).label,
        "base_windows": [serialize_interval(item) for item in day_base],
        "available_windows": [serialize_interval(item) for item in day_available],
        "events": day_events,
    }


def build_calendar_days(
    query_start, query_end, base_intervals, busy_intervals, events, timezone_name
):
    available_intervals = subtract_intervals(base_intervals, busy_intervals)
    days = []
    for day_value in iter_dates_in_range(query_start, query_end):
        days.append(
            build_day_payload(
                day_value,
                base_intervals,
                available_intervals,
                events,
                timezone_name,
            )
        )
    return days


def collect_appointment_busy_intervals(
    center, resource_type, resource_ids, range_start, range_end
):
    appointments = (
        Appointment.objects.filter(
            center=center,
            status__in=BUSY_APPOINTMENT_STATUSES,
            start_datetime__lt=range_end,
            end_datetime__gt=range_start,
        )
        .select_related(
            "customer_profile",
            "service",
            "room",
            "equipment",
        )
        .prefetch_related("associate_links__associate", "associate_links__role")
    )
    resource_id_set = None
    if resource_ids is not None:
        resource_id_set = {str(item) for item in resource_ids}
    intervals = []
    events = []
    for appointment in appointments:
        exclusive_interval = (
            appointment.exclusive_start_datetime,
            appointment.exclusive_end_datetime,
        )
        display_interval = (
            appointment.start_datetime,
            appointment.end_datetime,
        )
        include_interval = False
        if resource_type == "center":
            include_interval = True
        elif resource_type == "associate":
            for link in appointment.associate_links.all():
                if resource_id_set is None or str(link.associate_id) in resource_id_set:
                    include_interval = True
                    break
        elif resource_type == "room":
            if appointment.room_id and (
                resource_id_set is None
                or str(appointment.room_id) in resource_id_set
            ):
                include_interval = True
        elif resource_type == "equipment":
            if appointment.equipment_id and (
                resource_id_set is None
                or str(appointment.equipment_id) in resource_id_set
            ):
                include_interval = True
        if not include_interval:
            continue
        intervals.append(exclusive_interval)
        customer_name = " ".join(
            part
            for part in [
                appointment.customer_profile.first_name or "",
                appointment.customer_profile.last_name or "",
            ]
            if part
        ).strip()
        events.append(
            serialize_event(
                "appointment",
                appointment.pk,
                display_interval,
                {
                    "code": appointment.code,
                    "status": appointment.status,
                    "has_open_exception": appointment.has_open_exception,
                    "customer_name": customer_name or str(appointment.customer_profile_id),
                    "service_name": appointment.service.name,
                },
            )
        )
    return merge_intervals(intervals), events


def compute_center_calendar(center, start_date, granularity):
    query_start, query_end = resolve_query_date_range(start_date, granularity)
    timezone_name = get_center_timezone_name(center)
    base_intervals = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    closure_intervals, closure_events = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    appointment_intervals, appointment_events = collect_appointment_busy_intervals(
        center, "center", None, range_start, range_end
    )
    busy_intervals = merge_intervals(closure_intervals + appointment_intervals)
    events = closure_events + appointment_events
    days = build_calendar_days(
        query_start,
        query_end,
        base_intervals,
        busy_intervals,
        events,
        timezone_name,
    )
    return {
        "resource_type": "center",
        "center_id": str(center.pk),
        "timezone": timezone_name,
        "start": query_start.isoformat(),
        "end": query_end.isoformat(),
        "granularity": granularity,
        "days": days,
    }


def compute_associate_center_calendar(center, associate, start_date, granularity):
    query_start, query_end = resolve_query_date_range(start_date, granularity)
    timezone_name = get_center_timezone_name(center)
    center_hours = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    roster_hours = expand_roster_entries(
        center, associate, query_start, query_end, timezone_name
    )
    base_intervals = intersect_intervals(center_hours, roster_hours)
    block_intervals, block_events = collect_associate_block_events(
        center, associate, query_start, query_end, timezone_name
    )
    leave_intervals, leave_events = collect_associate_leave_events(
        center, associate, query_start, query_end, timezone_name
    )
    closure_intervals, closure_events = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    care_teams = live_care_teams_for_associate(center, associate)
    team_block_intervals, team_block_events = collect_care_team_block_events(
        center, care_teams, query_start, query_end, timezone_name
    )
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    appointment_intervals, appointment_events = collect_appointment_busy_intervals(
        center,
        "associate",
        [associate.pk],
        range_start,
        range_end,
    )
    busy_intervals = merge_intervals(
        block_intervals
        + leave_intervals
        + closure_intervals
        + team_block_intervals
        + appointment_intervals
    )
    events = (
        block_events
        + leave_events
        + closure_events
        + team_block_events
        + appointment_events
    )
    days = build_calendar_days(
        query_start,
        query_end,
        base_intervals,
        busy_intervals,
        events,
        timezone_name,
    )
    return {
        "resource_type": "associate",
        "center_id": str(center.pk),
        "associate_id": str(associate.pk),
        "timezone": timezone_name,
        "start": query_start.isoformat(),
        "end": query_end.isoformat(),
        "granularity": granularity,
        "days": days,
    }


def compute_care_team_calendar(center, care_team, start_date, granularity):
    query_start, query_end = resolve_query_date_range(start_date, granularity)
    timezone_name = get_center_timezone_name(center)
    associates = live_associates_for_care_team(center, care_team)
    center_hours = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    member_bases = []
    member_busy = []
    events = []
    for associate in associates:
        roster_hours = expand_roster_entries(
            center, associate, query_start, query_end, timezone_name
        )
        member_bases.append(intersect_intervals(center_hours, roster_hours))
        block_intervals, block_events = collect_associate_block_events(
            center, associate, query_start, query_end, timezone_name
        )
        leave_intervals, leave_events = collect_associate_leave_events(
            center, associate, query_start, query_end, timezone_name
        )
        member_busy.extend(block_intervals)
        member_busy.extend(leave_intervals)
        events.extend(events_with_associate_id(block_events, associate))
        events.extend(events_with_associate_id(leave_events, associate))
    if not member_bases:
        base_intervals = []
    else:
        base_intervals = member_bases[0]
        for member_base in member_bases[1:]:
            base_intervals = intersect_intervals(base_intervals, member_base)
    closure_intervals, closure_events = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    events.extend(closure_events)
    team_block_intervals, team_block_events = collect_care_team_block_events(
        center, [care_team], query_start, query_end, timezone_name
    )
    events.extend(team_block_events)
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    appointment_intervals, appointment_events = collect_appointment_busy_intervals(
        center,
        "associate",
        [associate.pk for associate in associates],
        range_start,
        range_end,
    )
    events.extend(appointment_events)
    busy_intervals = merge_intervals(
        member_busy
        + closure_intervals
        + team_block_intervals
        + appointment_intervals
    )
    days = build_calendar_days(
        query_start,
        query_end,
        base_intervals,
        busy_intervals,
        events,
        timezone_name,
    )
    return {
        "resource_type": "care_team",
        "center_id": str(center.pk),
        "care_team_id": str(care_team.pk),
        "timezone": timezone_name,
        "start": query_start.isoformat(),
        "end": query_end.isoformat(),
        "granularity": granularity,
        "days": days,
    }


def compute_room_calendar(center, room, start_date, granularity):
    query_start, query_end = resolve_query_date_range(start_date, granularity)
    timezone_name = get_center_timezone_name(center)
    base_intervals = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    block_intervals, block_events = collect_room_block_events(
        room, query_start, query_end, timezone_name
    )
    downtime_intervals, downtime_events = collect_room_downtime_events(
        room, query_start, query_end, timezone_name
    )
    closure_intervals, closure_events = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    appointment_intervals, appointment_events = collect_appointment_busy_intervals(
        center,
        "room",
        [room.pk],
        range_start,
        range_end,
    )
    busy_intervals = merge_intervals(
        block_intervals
        + downtime_intervals
        + closure_intervals
        + appointment_intervals
    )
    events = block_events + downtime_events + closure_events + appointment_events
    days = build_calendar_days(
        query_start,
        query_end,
        base_intervals,
        busy_intervals,
        events,
        timezone_name,
    )
    return {
        "resource_type": "room",
        "center_id": str(center.pk),
        "room_id": str(room.pk),
        "timezone": timezone_name,
        "start": query_start.isoformat(),
        "end": query_end.isoformat(),
        "granularity": granularity,
        "days": days,
    }


def compute_equipment_calendar(center, equipment, start_date, granularity):
    query_start, query_end = resolve_query_date_range(start_date, granularity)
    timezone_name = get_center_timezone_name(center)
    base_intervals = expand_center_operating_hours(
        center, query_start, query_end, timezone_name
    )
    block_intervals, block_events = collect_equipment_block_events(
        equipment, query_start, query_end, timezone_name
    )
    downtime_intervals, downtime_events = collect_equipment_downtime_events(
        equipment, query_start, query_end, timezone_name
    )
    closure_intervals, closure_events = collect_closure_events(
        center, query_start, query_end, timezone_name
    )
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    appointment_intervals, appointment_events = collect_appointment_busy_intervals(
        center,
        "equipment",
        [equipment.pk],
        range_start,
        range_end,
    )
    busy_intervals = merge_intervals(
        block_intervals
        + downtime_intervals
        + closure_intervals
        + appointment_intervals
    )
    events = block_events + downtime_events + closure_events + appointment_events
    days = build_calendar_days(
        query_start,
        query_end,
        base_intervals,
        busy_intervals,
        events,
        timezone_name,
    )
    return {
        "resource_type": "equipment",
        "center_id": str(center.pk),
        "equipment_id": str(equipment.pk),
        "timezone": timezone_name,
        "start": query_start.isoformat(),
        "end": query_end.isoformat(),
        "granularity": granularity,
        "days": days,
    }


def parse_calendar_query_params(request, default_granularity="day"):
    start_param = request.query_params.get("start")
    if start_param:
        start_date = date.fromisoformat(start_param)
    else:
        start_date = timezone.localdate()
    granularity = request.query_params.get("granularity", default_granularity)
    return start_date, granularity
