from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import NamedTuple

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts.associates.models import Associate, AssociateCenterAssignment
from appointments.models import AssociateAvailabilityBlock, AssociateLeave
from appointments.serializers import create_associate_availability_block
from appointments.utils.constants import AvailabilityOrigin, ExceptionSourceType, LeaveScope
from appointments.utils.exceptions import (
    apply_availability_exception_hooks,
    pick_exception_scan_status,
)
from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.tokens import get_valid_access_token

SYNC_WINDOW_DAYS = 30
FALLBACK_REASON = "Busy (Google Calendar)"
FALLBACK_LEAVE_REASON = "Leave (Google Calendar)"

RRULE_BYDAY_TO_DAY_OF_WEEK = {
    "MO": "0", "TU": "1", "WE": "2", "TH": "3", "FR": "4", "SA": "5", "SU": "6",
}
ALL_DAYS_OF_WEEK = list(RRULE_BYDAY_TO_DAY_OF_WEEK.values())


def _parse_rrule_until(until_value: str, start_dt: datetime):
    # Last date an occurrence can start on (UNTIL may be a date or a UTC/floating datetime).
    if "T" not in until_value:
        return datetime.strptime(until_value, "%Y%m%d").date()
    local_zone = timezone.get_current_timezone()
    zone = UTC if until_value.endswith("Z") else local_zone
    until_dt = (
        datetime.strptime(until_value.removesuffix("Z"), "%Y%m%dT%H%M%S")
        .replace(tzinfo=zone)
        .astimezone(local_zone)
    )
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
        if effective_until < start_dt.date():
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
    last_day = parse_date(end_date) - timedelta(days=1)
    return (
        datetime.combine(parse_date(start_date), time.min, tzinfo=zone),
        datetime.combine(last_day, time(23, 59, 59), tzinfo=zone),
    )


def _event_bounds(event: dict):
    start = event.get("start", {})
    end = event.get("end", {})
    if "dateTime" in start and "dateTime" in end:
        return (
            timezone.localtime(parse_datetime(start["dateTime"])),
            timezone.localtime(parse_datetime(end["dateTime"])),
        )
    if "date" in start and "date" in end:
        return _all_day_event_bounds(start["date"], end["date"])
    return None


def _is_leave_event(event: dict):
    # Biopeak leave has no recurrence, so recurring events stay blocks.
    if event.get("recurrence"):
        return False
    return event.get("eventType") == "outOfOffice" or "date" in event.get("start", {})


def build_spec_from_event(event: dict):
    # Returns None if the event shouldn't block anything; "kind" is "leave" or "block".
    if (
        event.get("status") == "cancelled"
        or event.get("transparency") == "transparent"
        or calendar_api.event_is_biopeak_outbound(event)
        or _is_declined_by_self(event)
    ):
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
    center_ids = frozenset(row.center_id for row in rows)
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


def _create_blocks(centers, associate, user, spec: dict):
    # No overlap check - Biopeak allows overlapping availability blocks.
    is_recurring = spec["is_recurring"]
    days_of_week = spec["days_of_week"] if is_recurring else [None]
    scan_results = []
    for center in centers:
        for day_of_week in days_of_week:
            block = create_associate_availability_block(
                center, associate, user, is_recurring,
                spec.get("start_datetime"), spec.get("end_datetime"), day_of_week,
                spec.get("recurring_start_time"), spec.get("recurring_end_time"),
                spec.get("effective_from"), spec.get("effective_until"),
                spec["reason"], True,
                google_event_id=spec["google_event_id"],
                origin=AvailabilityOrigin.GOOGLE,
            )
            scan_results.append(
                _run_exception_hooks(center, block, ExceptionSourceType.ASSOCIATE_BLOCK)
            )
    return scan_results


def _leave_state(rows: list):
    first = rows[0]
    return first.start_datetime, first.end_datetime, first.reason


def _leave_wanted_state(spec: dict, centers: list):
    return spec["start_datetime"], spec["end_datetime"], spec["reason"]


def _leave_is_live(leave, time_min):
    return leave.end_datetime > time_min


def _create_leave(centers, associate, user, spec: dict):
    leave = AssociateLeave.objects.create(
        associate=associate,
        scope=LeaveScope.ALL_CENTERS,
        center=None,
        start_datetime=spec["start_datetime"],
        end_datetime=spec["end_datetime"],
        reason=spec["reason"],
        created_by=user,
        google_event_id=spec["google_event_id"],
        origin=AvailabilityOrigin.GOOGLE,
    )
    return [
        _run_exception_hooks(center, leave, ExceptionSourceType.ASSOCIATE_LEAVE)
        for center in centers
    ]


class SpecHandler(NamedTuple):
    model: type
    state: Callable
    wanted_state: Callable
    is_live: Callable
    create: Callable


SPEC_HANDLERS = {
    "block": SpecHandler(
        AssociateAvailabilityBlock, _block_state, _block_wanted_state,
        _block_is_live, _create_blocks,
    ),
    "leave": SpecHandler(
        AssociateLeave, _leave_state, _leave_wanted_state,
        _leave_is_live, _create_leave,
    ),
}


def _deactivate(model, associate, event_ids: list):
    if not event_ids:
        return 0
    return model.objects.filter(
        associate=associate,
        google_event_id__in=event_ids,
        is_active=True,
        origin=AvailabilityOrigin.GOOGLE,
    ).update(is_active=False)


def sync_google_events_to_availability_blocks(user, connection):
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
    for event in calendar_api.list_events(access_token, time_min, time_max):
        spec = build_spec_from_event(event)
        if spec is not None:
            specs_by_kind[spec["kind"]][spec["google_event_id"]] = spec

    created = replaced = removed = 0
    scan_results = []
    with transaction.atomic():
        for kind, specs in specs_by_kind.items():
            handler = SPEC_HANDLERS[kind]
            rows_by_event_id = defaultdict(list)
            # Only Google-imported rows — never MANUAL outbound-synced rows.
            imported_rows = handler.model.objects.filter(
                associate=associate,
                is_active=True,
                origin=AvailabilityOrigin.GOOGLE,
            ).exclude(google_event_id="")
            for row in imported_rows:
                rows_by_event_id[row.google_event_id].append(row)

            gone_event_ids = [
                event_id
                for event_id, rows in rows_by_event_id.items()
                if event_id not in specs
                and any(handler.is_live(row, time_min) for row in rows)
            ]
            removed += _deactivate(handler.model, associate, gone_event_ids)

            for event_id, spec in specs.items():
                rows = rows_by_event_id.get(event_id)
                if rows:
                    if handler.state(rows) == handler.wanted_state(spec, centers):
                        continue
                    _deactivate(handler.model, associate, [event_id])
                    replaced += 1
                else:
                    created += 1
                scan_results.extend(handler.create(centers, associate, user, spec))

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
