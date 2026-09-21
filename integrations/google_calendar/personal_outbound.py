from datetime import UTC, datetime, time, timedelta

from django.utils import timezone

from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import AvailabilityOrigin
from integrations.google_calendar import calendar_api
from integrations.google_calendar.connections import (
    get_google_calendar_connection_for_user,
    google_calendar_connection_is_connected,
)
from integrations.google_calendar.google_sync import send_google_calendar_outbound_event
from integrations.google_calendar.tokens import get_valid_access_token

DAY_OF_WEEK_TO_BYDAY = {
    "0": "MO",
    "1": "TU",
    "2": "WE",
    "3": "TH",
    "4": "FR",
    "5": "SA",
    "6": "SU",
}


def personal_google_event_id(*, series_id=None, block=None, leave=None):
    if series_id is not None:
        return series_id.hex
    if block is not None:
        return block.pk.hex
    if leave is not None:
        return leave.pk.hex
    raise ValueError("personal_google_event_id requires series_id, block, or leave.")


def build_weekly_rrule(days_of_week, effective_until, recurring_end_time):
    byday_tokens = [
        DAY_OF_WEEK_TO_BYDAY[day]
        for day in sorted(days_of_week, key=int)
        if day in DAY_OF_WEEK_TO_BYDAY
    ]
    rule = f"FREQ=WEEKLY;BYDAY={','.join(byday_tokens)}"
    if effective_until is None:
        return [f"RRULE:{rule}"]
    local_zone = timezone.get_current_timezone()
    until_local = datetime.combine(
        effective_until, recurring_end_time or time(23, 59, 59), tzinfo=local_zone
    )
    until_utc = until_local.astimezone(UTC)
    rule = f"{rule};UNTIL={until_utc.strftime('%Y%m%dT%H%M%SZ')}"
    return [f"RRULE:{rule}"]


def leave_is_all_day(leave):
    start_local = timezone.localtime(leave.start_datetime)
    end_local = timezone.localtime(leave.end_datetime)
    return start_local.time() == time.min and end_local.time() == time(23, 59, 59)


def _delete_personal_event(connection, event_id):
    if not event_id:
        return
    access_token = get_valid_access_token(connection)
    calendar_api.delete_event(access_token, event_id)


def _persist_block_google_event_id(blocks, event_id):
    block_ids = [block.pk for block in blocks]
    AssociateAvailabilityBlock.objects.filter(pk__in=block_ids).update(
        google_event_id=event_id,
        updated_at=timezone.localtime(timezone.now()),
    )


def _persist_leave_google_event_id(leave, event_id):
    if leave.google_event_id == event_id:
        return
    leave.google_event_id = event_id
    leave.save(update_fields=["google_event_id", "updated_at"])


def _load_block_rows(*, series_id=None, block_id=None):
    queryset = AssociateAvailabilityBlock.objects.select_related("associate__user")
    if series_id is not None:
        return list(
            queryset.filter(series_id=series_id).order_by("day_of_week", "pk")
        )
    if block_id is not None:
        block = queryset.filter(pk=block_id).first()
        return [block] if block is not None else []
    return []


def _connection_for_associate_user(associate):
    connection = get_google_calendar_connection_for_user(associate.user)
    if not google_calendar_connection_is_connected(connection):
        return None, "Personal Google Calendar not connected"
    return connection, None


def sync_associate_blocks_to_personal_google(*, series_id=None, block_id=None):
    """
    Desired-state sync for manual associate blocks onto the associate's
    personal Google Calendar. Returns a skip-reason string, or None on success.
    """
    if series_id is None and block_id is not None:
        block = AssociateAvailabilityBlock.objects.filter(pk=block_id).first()
        if block is not None and block.series_id is not None:
            series_id = block.series_id
            block_id = None

    rows = _load_block_rows(series_id=series_id, block_id=block_id)
    if not rows:
        return "Associate availability block no longer exists"

    first = rows[0]
    if first.origin != AvailabilityOrigin.MANUAL:
        return "Availability block was imported from Google; not written back"

    connection, skip_reason = _connection_for_associate_user(first.associate)
    if skip_reason:
        return skip_reason

    active_rows = [row for row in rows if row.is_active]
    stored_event_id = next(
        (row.google_event_id for row in rows if row.google_event_id), ""
    )
    deterministic_id = personal_google_event_id(
        series_id=first.series_id, block=first if first.series_id is None else None
    )

    if not active_rows:
        _delete_personal_event(connection, stored_event_id or deterministic_id)
        return None

    title = (active_rows[0].reason or "Busy").strip() or "Busy"
    if active_rows[0].is_recurring:
        days_of_week = [row.day_of_week for row in active_rows if row.day_of_week]
        start = datetime.combine(
            active_rows[0].effective_from,
            active_rows[0].recurring_start_time,
            tzinfo=timezone.get_current_timezone(),
        )
        end = datetime.combine(
            active_rows[0].effective_from,
            active_rows[0].recurring_end_time,
            tzinfo=timezone.get_current_timezone(),
        )
        if end <= start:
            end = end + timedelta(days=1)
        recurrence = build_weekly_rrule(
            days_of_week,
            active_rows[0].effective_until,
            active_rows[0].recurring_end_time,
        )
        event_id = send_google_calendar_outbound_event(
            connection,
            title=title,
            start=start,
            end=end,
            notes=title,
            event_id=stored_event_id or deterministic_id,
            recurrence=recurrence,
        )
    else:
        event_id = send_google_calendar_outbound_event(
            connection,
            title=title,
            start=timezone.localtime(active_rows[0].start_datetime),
            end=timezone.localtime(active_rows[0].end_datetime),
            notes=title,
            event_id=stored_event_id or deterministic_id,
        )
    _persist_block_google_event_id(rows, event_id)
    return None


def sync_associate_leave_to_personal_google(leave_id):
    leave = AssociateLeave.objects.filter(pk=leave_id).select_related(
        "associate__user"
    ).first()
    if leave is None:
        return "Associate leave no longer exists"
    if leave.origin != AvailabilityOrigin.MANUAL:
        return "Leave was imported from Google; not written back"

    connection, skip_reason = _connection_for_associate_user(leave.associate)
    if skip_reason:
        return skip_reason

    deterministic_id = personal_google_event_id(leave=leave)
    stored_event_id = leave.google_event_id or deterministic_id

    if not leave.is_active:
        _delete_personal_event(connection, stored_event_id)
        return None

    title = (leave.reason or "Leave").strip() or "Leave"
    all_day = leave_is_all_day(leave)
    event_id = send_google_calendar_outbound_event(
        connection,
        title=title,
        start=timezone.localtime(leave.start_datetime),
        end=timezone.localtime(leave.end_datetime),
        notes=title,
        event_id=stored_event_id,
        all_day=all_day,
    )
    _persist_leave_google_event_id(leave, event_id)
    return None
