from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts.associates.models import Associate, AssociateCenterAssignment
from appointments.models import AssociateAvailabilityBlock
from appointments.serializers import create_associate_availability_block
from appointments.utils.constants import ExceptionSourceType
from appointments.utils.exceptions import (
    apply_availability_exception_hooks,
    pick_exception_scan_status,
)
from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.tokens import get_valid_access_token

SYNC_WINDOW_DAYS = 30
FALLBACK_REASON = "Busy (Google Calendar)"

RRULE_BYDAY_TO_DAY_OF_WEEK = {
    "MO": "0", "TU": "1", "WE": "2", "TH": "3", "FR": "4", "SA": "5", "SU": "6",
}


def parse_supported_weekly_rrule(recurrence_lines: list[str]):
    # Returns day_of_week codes for a simple never-ending weekly RRULE, or None
    # if unsupported (Biopeak recurring blocks have no end date/count).
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
    if rule_parts.get("FREQ") != "WEEKLY":
        return None
    if rule_parts.get("INTERVAL", "1") != "1":
        return None
    if "UNTIL" in rule_parts or "COUNT" in rule_parts:
        return None
    by_day = rule_parts.get("BYDAY")
    if not by_day:
        return None
    day_tokens = by_day.split(",")
    if not all(token in RRULE_BYDAY_TO_DAY_OF_WEEK for token in day_tokens):
        return None
    return [RRULE_BYDAY_TO_DAY_OF_WEEK[token] for token in day_tokens]


def _is_declined_by_self(event: dict):
    for attendee in event.get("attendees", []):
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return False


def _all_day_event_bounds(start_date: str, end_date: str):
    # Google's all-day end.date is exclusive, so the last blocked day is end_date - 1.
    zone = timezone.get_current_timezone()
    last_day = parse_date(end_date) - timedelta(days=1)
    return (
        datetime.combine(parse_date(start_date), time.min, tzinfo=zone),
        datetime.combine(last_day, time.max, tzinfo=zone),
    )


def build_block_spec_from_event(event: dict):
    # Returns None if the event shouldn't block anything in Biopeak.
    if event.get("status") == "cancelled":
        return None
    if event.get("transparency") == "transparent":
        return None
    if _is_declined_by_self(event):
        return None

    start = event.get("start", {})
    end = event.get("end", {})
    reason = (event.get("summary") or FALLBACK_REASON)[:255]

    if "dateTime" in start and "dateTime" in end:
        start_dt = timezone.localtime(parse_datetime(start["dateTime"]))
        end_dt = timezone.localtime(parse_datetime(end["dateTime"]))
    elif "date" in start and "date" in end:
        # All-day event (e.g. leave/out-of-office) - block the full day span.
        start_dt, end_dt = _all_day_event_bounds(start["date"], end["date"])
    else:
        return None  # unrecognized start/end shape

    recurrence = event.get("recurrence")
    if recurrence:
        days_of_week = parse_supported_weekly_rrule(recurrence)
        if days_of_week is None:
            return None
        return {
            "google_event_id": event["id"],
            "reason": reason,
            "is_recurring": True,
            "days_of_week": days_of_week,
            "recurring_start_time": start_dt.time(),
            "recurring_end_time": end_dt.time(),
            "effective_from": start_dt.date(),
        }
    return {
        "google_event_id": event["id"],
        "reason": reason,
        "is_recurring": False,
        "start_datetime": start_dt,
        "end_datetime": end_dt,
    }


def _spec_signature(spec: dict):
    if spec["is_recurring"]:
        return (
            True,
            frozenset(spec["days_of_week"]),
            spec["recurring_start_time"],
            spec["recurring_end_time"],
            spec["effective_from"],
            spec["reason"],
        )
    return (False, spec["start_datetime"], spec["end_datetime"], spec["reason"])


def _existing_block_state(associate, google_event_id: str):
    # Lets a re-sync tell "nothing changed" apart from "needs replacing".
    rows = list(
        AssociateAvailabilityBlock.objects.filter(
            associate=associate, google_event_id=google_event_id, is_active=True
        )
    )
    if not rows:
        return None
    center_ids = frozenset(row.center_id for row in rows)
    first = rows[0]
    if first.is_recurring:
        days = frozenset(row.day_of_week for row in rows)
        signature = (
            True, days, first.recurring_start_time, first.recurring_end_time,
            first.effective_from, first.reason,
        )
    else:
        signature = (False, first.start_datetime, first.end_datetime, first.reason)
    return center_ids, signature


def _create_blocks_for_spec(centers, associate, user, spec: dict):
    # No overlap check - Biopeak allows overlapping availability blocks.
    created_blocks = []
    for center in centers:
        if spec["is_recurring"]:
            for day_of_week in spec["days_of_week"]:
                created_blocks.append(create_associate_availability_block(
                    center, associate, user, True, None, None, day_of_week,
                    spec["recurring_start_time"], spec["recurring_end_time"],
                    spec["effective_from"], None, spec["reason"], True,
                    google_event_id=spec["google_event_id"],
                ))
        else:
            created_blocks.append(create_associate_availability_block(
                center, associate, user, False,
                spec["start_datetime"], spec["end_datetime"], None,
                None, None, None, None, spec["reason"], True,
                google_event_id=spec["google_event_id"],
            ))
    return created_blocks


def sync_google_events_to_availability_blocks(user, connection):
    # Desired-states the user's Google events onto their AssociateAvailabilityBlock rows.
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

    specs_by_event_id = {}
    for event in calendar_api.list_events(access_token, time_min, time_max):
        spec = build_block_spec_from_event(event)
        if spec is not None:
            specs_by_event_id[spec["google_event_id"]] = spec

    created_count = 0
    replaced_count = 0
    removed_count = 0
    scan_results = []

    with transaction.atomic():
        # Excludes already-ended one-off blocks, which naturally drop out of
        # Google's fetch too, so their absence isn't mistaken for "removed".
        existing_event_ids = set(
            AssociateAvailabilityBlock.objects.filter(
                associate=associate, is_active=True
            )
            .exclude(google_event_id="")
            .filter(Q(is_recurring=True) | Q(end_datetime__gt=time_min))
            .values_list("google_event_id", flat=True)
            .distinct()
        )

        gone_event_ids = existing_event_ids - specs_by_event_id.keys()
        if gone_event_ids:
            removed_count = AssociateAvailabilityBlock.objects.filter(
                associate=associate, google_event_id__in=gone_event_ids, is_active=True,
            ).update(is_active=False)

        desired_center_ids = frozenset(center.pk for center in centers)
        for spec in specs_by_event_id.values():
            state = _existing_block_state(associate, spec["google_event_id"])
            if state is not None and state == (desired_center_ids, _spec_signature(spec)):
                continue  # already in sync, nothing to write

            if state is not None:
                AssociateAvailabilityBlock.objects.filter(
                    associate=associate,
                    google_event_id=spec["google_event_id"],
                    is_active=True,
                ).update(is_active=False)
            new_blocks = _create_blocks_for_spec(centers, associate, user, spec)

            replaced_count += 1 if state is not None else 0
            created_count += 1 if state is None else 0
            for block in new_blocks:
                scan_results.append(apply_availability_exception_hooks(
                    center=block.center,
                    instance=block,
                    source_type=ExceptionSourceType.ASSOCIATE_BLOCK,
                    validated_data={},
                    created=True,
                ))

    connection.last_synced_at = timezone.localtime(timezone.now())
    connection.save(update_fields=["last_synced_at", "updated_at"])

    logger.info(
        f"Google Calendar availability sync for user {user.pk}: "
        f"{created_count} created, {replaced_count} replaced, {removed_count} removed."
    )

    return {
        "synced": True,
        "created": created_count,
        "replaced": replaced_count,
        "removed": removed_count,
        "exception_scan": pick_exception_scan_status(scan_results),
    }
