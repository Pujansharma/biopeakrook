from rest_framework import serializers

from accounts.centers.models import CenterOperatingHour
from appointments.models import AssociateRosterEntry
from appointments.utils.constants import (
    AFTER_CLOSING,
    AFTER_CLOSING_MESSAGE,
    BEFORE_OPENING,
    BEFORE_OPENING_MESSAGE,
    OPERATING_HOURS_ROSTER_ERROR,
    ROSTER_AFTER_NEW_CLOSING_MESSAGE,
    ROSTER_BEFORE_NEW_OPENING_MESSAGE,
    ROSTER_HOURS_ERROR,
    ROSTER_ON_CLOSED_DAY,
    ROSTER_ON_CLOSED_DAY_MESSAGE,
    UNAVAILABLE_DAY_ERROR,
)
from core.utils.constants import AppointmentDays


def format_clock_time(value):
    return value.strftime("%H:%M:%S")


def day_of_week_name(day_of_week):
    return AppointmentDays(str(day_of_week)).label


def unique_values(values):
    return list(dict.fromkeys(values))


def roster_bound_error(code, field, message, associate_ids=None):
    error = {"code": code, "field": field, "message": message}
    if associate_ids is not None:
        error["associate_ids"] = associate_ids
    return error


def day_error_payload(day_of_week, errors, open_time=None, close_time=None):
    payload = {
        "day_of_week": str(day_of_week),
        "day_of_week_name": day_of_week_name(day_of_week),
        "errors": errors,
    }
    if open_time is not None and close_time is not None:
        payload["open_time"] = format_clock_time(open_time)
        payload["close_time"] = format_clock_time(close_time)
    return payload


def load_active_operating_hours_by_day(center, day_values):
    rows = CenterOperatingHour.objects.filter(
        center=center,
        is_active=True,
        day_of_week__in=day_values,
    ).order_by("-created_at")
    open_by_day = {}
    closed_days = set()
    for operating_hour in rows:
        if (
            operating_hour.is_open
            and operating_hour.open_time is not None
            and operating_hour.close_time is not None
        ):
            if operating_hour.day_of_week not in open_by_day:
                open_by_day[operating_hour.day_of_week] = operating_hour
            continue
        if not operating_hour.is_open:
            closed_days.add(operating_hour.day_of_week)
    return open_by_day, closed_days


def collect_roster_day_errors(center, entries):
    day_values = [str(entry["day_of_week"]) for entry in entries]
    open_by_day, closed_days = load_active_operating_hours_by_day(center, day_values)
    day_errors = []
    for entry in entries:
        day_of_week = str(entry["day_of_week"])
        operating_hour = open_by_day.get(day_of_week)
        if operating_hour is None:
            code, message = UNAVAILABLE_DAY_ERROR[day_of_week in closed_days]
            day_errors.append(
                day_error_payload(
                    day_of_week,
                    [roster_bound_error(code, "day_of_week", message)],
                )
            )
            continue
        errors = []
        if entry["start_time"] < operating_hour.open_time:
            errors.append(
                roster_bound_error(
                    BEFORE_OPENING, "start_time", BEFORE_OPENING_MESSAGE
                )
            )
        if entry["end_time"] > operating_hour.close_time:
            errors.append(
                roster_bound_error(AFTER_CLOSING, "end_time", AFTER_CLOSING_MESSAGE)
            )
        if errors:
            day_errors.append(
                day_error_payload(
                    day_of_week,
                    errors,
                    operating_hour.open_time,
                    operating_hour.close_time,
                )
            )
    return day_errors


def assert_roster_within_operating_hours(center, entries):
    day_errors = collect_roster_day_errors(center, entries)
    if not day_errors:
        return
    raise serializers.ValidationError(
        {
            "non_field_errors": [ROSTER_HOURS_ERROR],
            "day_errors": day_errors,
        }
    )


def group_active_roster_by_day(center, day_values):
    roster_rows = AssociateRosterEntry.objects.filter(
        center=center,
        is_active=True,
        day_of_week__in=day_values,
    ).select_related("associate")
    roster_by_day = {}
    for roster_entry in roster_rows:
        roster_by_day.setdefault(roster_entry.day_of_week, []).append(roster_entry)
    return roster_by_day


def collect_operating_hours_roster_conflicts(
    center, open_days, closed_days, open_time, close_time
):
    affected_days = list(open_days) + list(closed_days)
    if not affected_days:
        return []
    roster_by_day = group_active_roster_by_day(center, affected_days)
    day_errors = []
    for day_of_week in open_days:
        day_roster = roster_by_day.get(day_of_week, [])
        before_ids = []
        after_ids = []
        for roster_entry in day_roster:
            if roster_entry.start_time < open_time:
                before_ids.append(str(roster_entry.associate.pk))
            if roster_entry.end_time > close_time:
                after_ids.append(str(roster_entry.associate.pk))
        errors = []
        if before_ids:
            errors.append(
                roster_bound_error(
                    BEFORE_OPENING,
                    "open_time",
                    ROSTER_BEFORE_NEW_OPENING_MESSAGE,
                    unique_values(before_ids),
                )
            )
        if after_ids:
            errors.append(
                roster_bound_error(
                    AFTER_CLOSING,
                    "close_time",
                    ROSTER_AFTER_NEW_CLOSING_MESSAGE,
                    unique_values(after_ids),
                )
            )
        if errors:
            day_errors.append(
                day_error_payload(day_of_week, errors, open_time, close_time)
            )
    for day_of_week in closed_days:
        day_roster = roster_by_day.get(day_of_week, [])
        if not day_roster:
            continue
        associate_ids = unique_values(
            [str(roster_entry.associate.pk) for roster_entry in day_roster]
        )
        day_errors.append(
            day_error_payload(
                day_of_week,
                [
                    roster_bound_error(
                        ROSTER_ON_CLOSED_DAY,
                        "day_of_week",
                        ROSTER_ON_CLOSED_DAY_MESSAGE,
                        associate_ids,
                    )
                ],
            )
        )
    return day_errors


def assert_operating_hours_cover_roster(
    center, open_days, closed_days, open_time, close_time
):
    day_errors = collect_operating_hours_roster_conflicts(
        center, open_days, closed_days, open_time, close_time
    )
    if not day_errors:
        return
    raise serializers.ValidationError(
        {
            "non_field_errors": [OPERATING_HOURS_ROSTER_ERROR],
            "day_errors": day_errors,
        }
    )
