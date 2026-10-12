from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import NamedTuple

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts.associates.models import Associate, AssociateCenterAssignment
from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.serializers import create_associate_availability_block
from appointments.utils.constants import AvailabilityOrigin, ExceptionSourceType, LeaveScope
from appointments.utils.exceptions import (
    apply_availability_exception_hooks,
    pick_exception_scan_status,
    trigger_exception_resolution,
)
from appointments.utils.operations import invalidate_operations_cache
from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.connections import connection_is_shared_organizer
from integrations.google_calendar.tokens import get_valid_access_token

SYNC_WINDOW_DAYS = 30
FALLBACK_REASON = "Busy (Google Calendar)"
FALLBACK_LEAVE_REASON = "Leave (Google Calendar)"

RRULE_BYDAY_TO_DAY_OF_WEEK = {
    "MO": "0", "TU": "1", "WE": "2", "TH": "3", "FR": "4", "SA": "5", "SU": "6",
}
ALL_DAYS_OF_WEEK = list(RRULE_BYDAY_TO_DAY_OF_WEEK.values())


def _parse_aware_datetime(value: str):
    # Google's text is outside our control: unparsable or timezone-less -> None
    try:
        parsed = parse_datetime(value)
    except ValueError:
        return None
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed


def _parse_date_or_none(value: str):
    try:
        return parse_date(value)
    except ValueError:
        return None


def _parse_rrule_until(until_value: str, start_dt: datetime):
    # Last date an occurrence can start on (UNTIL may be a date or a UTC/floating datetime).
    # Returns None when UNTIL is malformed.
    local_zone = timezone.get_current_timezone()
    zone = UTC if until_value.endswith("Z") else local_zone
    date_format = "%Y%m%dT%H%M%S" if "T" in until_value else "%Y%m%d"
    try:
        parsed = datetime.strptime(until_value.removesuffix("Z"), date_format)
    except ValueError:
        return None
    if "T" not in until_value:
        return parsed.date()
    until_dt = parsed.replace(tzinfo=zone).astimezone(local_zone)
    if until_dt.time() >= start_dt.time():
        return until_dt.date()
    return until_dt.date() - timedelta(days=1)


def _rrule_days_of_week(rule_parts: dict, start_dt: datetime):
    day_tokens = rule_parts["BYDAY"].split(",") if rule_parts.get("BYDAY") else []
    if not all(token in RRULE_BYDAY_TO_DAY_OF_WEEK for token in day_tokens):
        return None
    if day_tokens:
        return [RRULE_BYDAY_TO_DAY_OF_WEEK[token] for token in day_tokens]
    default_days = {"DAILY": ALL_DAYS_OF_WEEK, "WEEKLY": [str(start_dt.weekday())]}
    return default_days[rule_parts["FREQ"]]


def parse_supported_rrule(recurrence_lines: list[str], start_dt: datetime):
    # Daily/weekly every-1 rules only; COUNT, INTERVAL>1, monthly, yearly return None.
    rrule_line = next(
        (line for line in recurrence_lines if line.startswith("RRULE:")), None
    )
    if rrule_line is None:
        return None
    rule_parts = dict(
        part.split("=", 1)
        for part in rrule_line.removeprefix("RRULE:").split(";")
        if "=" in part
    )
    if rule_parts.get("FREQ") not in {"DAILY", "WEEKLY"}:
        return None
    if rule_parts.get("INTERVAL", "1") != "1" or "COUNT" in rule_parts:
        return None
    days_of_week = _rrule_days_of_week(rule_parts, start_dt)
    if days_of_week is None:
        return None
    effective_until = None
    if "UNTIL" in rule_parts:
        effective_until = _parse_rrule_until(rule_parts["UNTIL"], start_dt)
        if effective_until is None or effective_until < start_dt.date():
            return None
    return {"days_of_week": days_of_week, "effective_until": effective_until}


def _is_declined_by_self(event: dict):
    return any(
        attendee.get("self") and attendee.get("responseStatus") == "declined"
        for attendee in event.get("attendees", [])
    )


def _all_day_event_bounds(start_date: str, end_date: str):
    # Google's all-day end.date is exclusive.
    zone = timezone.get_current_timezone()
    first_day = _parse_date_or_none(start_date)
    exclusive_end = _parse_date_or_none(end_date)
    if first_day is None or exclusive_end is None:
        return None
    last_day = exclusive_end - timedelta(days=1)
    return (
        datetime.combine(first_day, time.min, tzinfo=zone),
        datetime.combine(last_day, time(23, 59, 59), tzinfo=zone),
    )


def _event_bounds(event: dict):
    start = event.get("start", {})
    end = event.get("end", {})
    if "dateTime" in start and "dateTime" in end:
        start_dt = _parse_aware_datetime(start["dateTime"])
        end_dt = _parse_aware_datetime(end["dateTime"])
        if start_dt is None or end_dt is None:
            return None
        return timezone.localtime(start_dt), timezone.localtime(end_dt)
    if "date" in start and "date" in end:
        return _all_day_event_bounds(start["date"], end["date"])
    return None


def _is_leave_event(event: dict):
    # Biopeak leave has no recurrence, so recurring events stay blocks.
    if event.get("recurrence"):
        return False
    return event.get("eventType") == "outOfOffice" or "date" in event.get("start", {})


def _google_marks_free(event: dict):
    # Google itself says the event no longer blocks the person's time
    return (
        event.get("status") == "cancelled"
        or event.get("transparency") == "transparent"
        or _is_declined_by_self(event)
    )


def _is_biopeak_event(event: dict):
    return (
        calendar_api.event_is_biopeak_outbound(event)
        or calendar_api.event_is_appointment(event)
        or calendar_api.event_is_organized_by(
            event, getattr(settings, "GOOGLE_CALENDAR_ID", None)
        )
    )


def should_skip_inbound(event: dict):
    # Skipped events take the "gone" path in sync, so rows imported from them
    # earlier are removed. Unreadable events are different: they keep their rows.
    return _google_marks_free(event) or _is_biopeak_event(event)


def build_spec_from_event(event: dict):
    if should_skip_inbound(event):
        return None

    bounds = _event_bounds(event)
    if bounds is None:
        return None
    start_dt, end_dt = bounds

    is_leave = _is_leave_event(event)
    fallback_reason = FALLBACK_LEAVE_REASON if is_leave else FALLBACK_REASON
    spec = {
        "google_event_id": event["id"],
        "reason": (event.get("summary") or fallback_reason)[:255],
    }

    if is_leave:
        return {**spec, "kind": "leave", "start_datetime": start_dt, "end_datetime": end_dt}

    recurrence = event.get("recurrence")
    if not recurrence:
        return {
            **spec, "kind": "block", "is_recurring": False,
            "start_datetime": start_dt, "end_datetime": end_dt,
        }

    rule = parse_supported_rrule(recurrence, start_dt)
    if rule is None:
        return None
    return {
        **spec,
        "kind": "block",
        "is_recurring": True,
        "days_of_week": rule["days_of_week"],
        "recurring_start_time": start_dt.time(),
        "recurring_end_time": end_dt.time(),
        "effective_from": start_dt.date(),
        "effective_until": rule["effective_until"],
    }


def _run_exception_hooks(center, instance, source_type):
    return apply_availability_exception_hooks(
        center=center,
        instance=instance,
        source_type=source_type,
        validated_data={},
        created=True,
    )


def _block_state(rows: list):
    first = rows[0]
    center_ids = frozenset(row.center.pk for row in rows)
    if first.is_recurring:
        return center_ids, (
            True, frozenset(row.day_of_week for row in rows),
            first.recurring_start_time, first.recurring_end_time,
            first.effective_from, first.effective_until, first.reason,
        )
    return center_ids, (False, first.start_datetime, first.end_datetime, first.reason)


def _block_wanted_state(spec: dict, centers: list):
    center_ids = frozenset(center.pk for center in centers)
    if spec["is_recurring"]:
        return center_ids, (
            True, frozenset(spec["days_of_week"]),
            spec["recurring_start_time"], spec["recurring_end_time"],
            spec["effective_from"], spec["effective_until"], spec["reason"],
        )
    return center_ids, (False, spec["start_datetime"], spec["end_datetime"], spec["reason"])


def _block_is_live(block, time_min):
    # Ended one-off blocks drop out of Google's fetch on their own; not "removed".
    return block.is_recurring or block.end_datetime > time_min


class WantedRow(NamedTuple):
    center: object  # None for all-centers leave
    day_of_week: str | None
    fields: dict  # every editable column of the new row
    hook_centers: list  # centers whose exception scan must run for this row


def _block_wanted_rows(spec: dict, centers: list):
    if spec["is_recurring"]:
        fields = {
            "is_recurring": True,
            "start_datetime": None,
            "end_datetime": None,
            "recurring_start_time": spec["recurring_start_time"],
            "recurring_end_time": spec["recurring_end_time"],
            "effective_from": spec["effective_from"],
            "effective_until": spec["effective_until"],
            "reason": spec["reason"],
        }
        days_of_week = spec["days_of_week"]
    else:
        fields = {
            "is_recurring": False,
            "start_datetime": spec["start_datetime"],
            "end_datetime": spec["end_datetime"],
            "recurring_start_time": None,
            "recurring_end_time": None,
            "effective_from": None,
            "effective_until": None,
            "reason": spec["reason"],
        }
        days_of_week = [None]
    return {
        (center.pk, day_of_week): WantedRow(center, day_of_week, fields, [center])
        for center in centers
        for day_of_week in days_of_week
    }


def _create_block_row(centers, associate, user, spec: dict, wanted: WantedRow):
    # No overlap check - Biopeak allows overlapping availability blocks.
    return create_associate_availability_block(
        center=wanted.center,
        associate=associate,
        created_by=user,
        day_of_week=wanted.day_of_week,
        is_active=True,
        google_event_id=spec["google_event_id"],
        origin=AvailabilityOrigin.GOOGLE,
        **wanted.fields,
    )


def _leave_state(rows: list):
    first = rows[0]
    return first.start_datetime, first.end_datetime, first.reason


def _leave_wanted_state(spec: dict, centers: list):
    return spec["start_datetime"], spec["end_datetime"], spec["reason"]


def _leave_is_live(leave, time_min):
    return leave.end_datetime > time_min


def _leave_wanted_rows(spec: dict, centers: list):
    fields = {
        "start_datetime": spec["start_datetime"],
        "end_datetime": spec["end_datetime"],
        "reason": spec["reason"],
    }
    return {(None, None): WantedRow(None, None, fields, centers)}


def _create_leave_row(centers, associate, user, spec: dict, wanted: WantedRow):
    return AssociateLeave.objects.create(
        associate=associate,
        scope=LeaveScope.ALL_CENTERS,
        center=None,
        created_by=user,
        google_event_id=spec["google_event_id"],
        origin=AvailabilityOrigin.GOOGLE,
        **wanted.fields,
    )


class SpecHandler(NamedTuple):
    model: type
    source_type: str
    state: Callable
    wanted_state: Callable
    is_live: Callable
    wanted_rows: Callable
    create_row: Callable


SPEC_HANDLERS = {
    "block": SpecHandler(
        AssociateAvailabilityBlock, ExceptionSourceType.ASSOCIATE_BLOCK, _block_state,
        _block_wanted_state, _block_is_live, _block_wanted_rows,
        _create_block_row,
    ),
    "leave": SpecHandler(
        AssociateLeave, ExceptionSourceType.ASSOCIATE_LEAVE, _leave_state,
        _leave_wanted_state, _leave_is_live, _leave_wanted_rows,
        _create_leave_row,
    ),
}


def _deactivate_rows(handler, row_pks: list):
    handler.model.objects.filter(pk__in=row_pks).update(
        is_active=False, updated_at=timezone.localtime(timezone.now())
    )
    return row_pks


def _deactivate_event_rows(handler, associate, event_ids: list):
    # Soft-off (never hard-delete): the same thing a manual is_active=false does.
    if not event_ids:
        return []
    row_pks = list(
        handler.model.objects.filter(
            associate=associate,
            google_event_id__in=event_ids,
            is_active=True,
            origin=AvailabilityOrigin.GOOGLE,
        ).values_list("pk", flat=True)
    )
    return _deactivate_rows(handler, row_pks)


def _resolve_deactivated(handler, centers: list, row_pks: list):
    # Same follow-up the manual "is_active=false" PATCH runs.
    for row_pk in row_pks:
        trigger_exception_resolution(handler.source_type, row_pk)
    if row_pks:
        for center in centers:
            invalidate_operations_cache(center.pk)


class EventChanges(NamedTuple):
    deactivated_pks: list
    created: list  # (center, row) pairs needing an exception scan


def _apply_event(handler, associate, user, centers, spec: dict, rows: list):
    # Edited event: old rows go inactive, fresh rows are created. One event = one
    # short transaction, so a failure never rolls back other events.
    try:
        with transaction.atomic():
            deactivated_pks = _deactivate_rows(handler, [row.pk for row in rows])
            created = []
            for wanted in handler.wanted_rows(spec, centers).values():
                row = handler.create_row(centers, associate, user, spec, wanted)
                created.extend((center, row) for center in wanted.hook_centers)
    except IntegrityError:
        logger.info(
            f"Google Calendar sync: event {spec['google_event_id']} was written "
            f"by a concurrent sync; skipping."
        )
        return None
    return EventChanges(deactivated_pks, created)


def _imported_rows_by_event_id(handler, associate):
    rows_by_event_id = defaultdict(list)
    # Only Google-imported rows - never MANUAL outbound-synced rows.
    imported_rows = (
        handler.model.objects.filter(
            associate=associate,
            is_active=True,
            origin=AvailabilityOrigin.GOOGLE,
        )
        .exclude(google_event_id="")
        .select_related("center")
    )
    for row in imported_rows:
        rows_by_event_id[row.google_event_id].append(row)
    return rows_by_event_id


def _sync_kind(
    handler, associate, user, centers, specs: dict, unreadable_event_ids: set, time_min
):
    rows_by_event_id = _imported_rows_by_event_id(handler, associate)
    created = replaced = 0
    scan_results = []

    gone_event_ids = [
        event_id
        for event_id, rows in rows_by_event_id.items()
        if event_id not in specs
        and event_id not in unreadable_event_ids
        and any(handler.is_live(row, time_min) for row in rows)
    ]
    gone_pks = _deactivate_event_rows(handler, associate, gone_event_ids)
    _resolve_deactivated(handler, centers, gone_pks)
    removed = len(gone_pks)

    for event_id, spec in specs.items():
        rows = rows_by_event_id.get(event_id)
        if rows and handler.state(rows) == handler.wanted_state(spec, centers):
            continue
        changes = _apply_event(handler, associate, user, centers, spec, rows or [])
        if changes is None:
            continue
        # Exception scans run after the event's transaction has committed.
        _resolve_deactivated(handler, centers, changes.deactivated_pks)
        scan_results.extend(
            _run_exception_hooks(center, row, handler.source_type)
            for center, row in changes.created
        )
        if rows:
            replaced += 1
        else:
            created += 1
    return created, replaced, removed, scan_results


def sync_google_events_to_availability_blocks(user, connection):
    if connection_is_shared_organizer(connection):
        return {"synced": False, "reason": "The shared appointment calendar is never synced as availability"}

    associate = Associate.objects.filter(pk=user.pk, is_active=True).first()
    if associate is None:
        return {"synced": False, "reason": "No active associate profile to sync availability for."}

    centers = [
        assignment.center
        for assignment in AssociateCenterAssignment.objects.filter(
            associate=associate, is_active=True
        ).select_related("center")
    ]
    if not centers:
        return {"synced": False, "reason": "No active center assignment to sync availability for."}

    access_token = get_valid_access_token(connection)
    time_min = timezone.localtime(timezone.now())
    time_max = time_min + timedelta(days=SYNC_WINDOW_DAYS)

    specs_by_kind = {"block": {}, "leave": {}}
    unreadable_event_ids = set()
    for event in calendar_api.list_events(access_token, time_min, time_max):
        spec = build_spec_from_event(event)
        if spec is not None:
            specs_by_kind[spec["kind"]][spec["google_event_id"]] = spec
        elif not should_skip_inbound(event):
            unreadable_event_ids.add(event["id"])

    created = replaced = removed = 0
    scan_results = []
    for kind, specs in specs_by_kind.items():
        kind_created, kind_replaced, kind_removed, kind_scans = _sync_kind(
            SPEC_HANDLERS[kind], associate, user, centers, specs,
            unreadable_event_ids, time_min,
        )
        created += kind_created
        replaced += kind_replaced
        removed += kind_removed
        scan_results.extend(kind_scans)

    connection.last_synced_at = timezone.localtime(timezone.now())
    connection.save(update_fields=["last_synced_at", "updated_at"])

    logger.info(
        f"Google Calendar availability sync for user {user.pk}: "
        f"{created} created, {replaced} replaced, {removed} removed."
    )

    return {
        "synced": True,
        "created": created,
        "replaced": replaced,
        "removed": removed,
        "exception_scan": pick_exception_scan_status(scan_results),
    }
