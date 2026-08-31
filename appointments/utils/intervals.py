from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from appointments.utils.constants import AvailabilityGranularity

UTC = ZoneInfo("UTC")


def merge_intervals(intervals):
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda item: item[0])
    merged = [sorted_intervals[0]]
    for interval_start, interval_end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if interval_start <= last_end:
            merged[-1] = (last_start, max(last_end, interval_end))
        else:
            merged.append((interval_start, interval_end))
    return merged


def intersect_intervals(first_intervals, second_intervals):
    if not first_intervals or not second_intervals:
        return []
    first_sorted = sorted(first_intervals, key=lambda item: item[0])
    second_sorted = sorted(second_intervals, key=lambda item: item[0])
    results = []
    second_index = 0
    second_length = len(second_sorted)
    for first_start, first_end in first_sorted:
        while second_index < second_length and second_sorted[second_index][1] <= first_start:
            second_index += 1
        scan_index = second_index
        while scan_index < second_length and second_sorted[scan_index][0] < first_end:
            second_start, second_end = second_sorted[scan_index]
            overlap_start = max(first_start, second_start)
            overlap_end = min(first_end, second_end)
            if overlap_start < overlap_end:
                results.append((overlap_start, overlap_end))
            scan_index += 1
    return merge_intervals(results)


def subtract_intervals(available_intervals, busy_intervals):
    if not available_intervals:
        return []
    if not busy_intervals:
        return list(available_intervals)
    busy_merged = merge_intervals(busy_intervals)
    results = []
    for available_start, available_end in available_intervals:
        cursor = available_start
        for busy_start, busy_end in busy_merged:
            if busy_end <= cursor:
                continue
            if busy_start >= available_end:
                break
            if busy_start > cursor:
                results.append((cursor, min(busy_start, available_end)))
            cursor = max(cursor, busy_end)
            if cursor >= available_end:
                break
        if cursor < available_end:
            results.append((cursor, available_end))
    return results


def expand_weekly_time_windows(
    query_start,
    query_end,
    day_of_week,
    start_time,
    end_time,
    timezone_name,
    effective_from=None,
    effective_until=None,
):
    zone = ZoneInfo(timezone_name)
    target_weekday = int(day_of_week)
    range_start = query_start
    range_end = query_end
    if effective_from and effective_from > range_start:
        range_start = effective_from
    if effective_until and effective_until < range_end:
        range_end = effective_until
    if range_start > range_end:
        return []

    results = []
    current_day = range_start
    while current_day <= range_end:
        if current_day.weekday() == target_weekday:
            start_local = datetime.combine(current_day, start_time, tzinfo=zone)
            end_local = datetime.combine(current_day, end_time, tzinfo=zone)
            results.append(
                (start_local.astimezone(UTC), end_local.astimezone(UTC))
            )
        current_day += timedelta(days=1)
    return results


def full_day_interval(day_value, timezone_name):
    zone = ZoneInfo(timezone_name)
    day_start = datetime.combine(day_value, time.min, tzinfo=zone)
    day_end = datetime.combine(day_value, time.max, tzinfo=zone)
    return day_start.astimezone(UTC), day_end.astimezone(UTC)


def clip_intervals_to_range(intervals, range_start, range_end):
    clipped = []
    for interval_start, interval_end in intervals:
        overlap_start = max(interval_start, range_start)
        overlap_end = min(interval_end, range_end)
        if overlap_start < overlap_end:
            clipped.append((overlap_start, overlap_end))
    return clipped


def resolve_query_date_range(start_date, granularity):
    if granularity == AvailabilityGranularity.WEEK:
        week_start = start_date - timedelta(days=start_date.weekday())
        return week_start, week_start + timedelta(days=6)
    if granularity == AvailabilityGranularity.MONTH:
        month_start = start_date.replace(day=1)
        if start_date.month == 12:
            next_month = date(start_date.year + 1, 1, 1)
        else:
            next_month = date(start_date.year, start_date.month + 1, 1)
        return month_start, next_month - timedelta(days=1)
    return start_date, start_date


def datetime_range_for_dates(query_start, query_end, timezone_name):
    zone = ZoneInfo(timezone_name)
    range_start = datetime.combine(query_start, time.min, tzinfo=zone).astimezone(UTC)
    range_end = datetime.combine(query_end, time.max, tzinfo=zone).astimezone(UTC)
    return range_start, range_end


def split_into_slots(free_windows, duration_minutes, step_minutes):
    if not free_windows or duration_minutes <= 0 or step_minutes <= 0:
        return []
    duration_delta = timedelta(minutes=duration_minutes)
    step_delta = timedelta(minutes=step_minutes)
    slots = []
    for window_start, window_end in free_windows:
        cursor = window_start
        while cursor + duration_delta <= window_end:
            slots.append((cursor, cursor + duration_delta))
            cursor += step_delta
    return sorted(slots, key=lambda item: item[0])
