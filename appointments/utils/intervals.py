from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

type Interval = tuple[datetime, datetime]

IST = ZoneInfo("Asia/Kolkata")


def expand_weekly_schedule(
    day_of_week: str,
    start_time: time,
    end_time: time,
    query_start: date,
    query_end: date,
    valid_from: date | None = None,
    valid_until: date | None = None,
) -> list[Interval]:
    """
    Expand a recurring weekly schedule rule into concrete datetime intervals
    within the query range.

    day_of_week: '0' (Monday) through '6' (Sunday), matching AppointmentDays.
    """
    target_weekday = int(day_of_week)
    effective_start = max(query_start, valid_from) if valid_from else query_start
    effective_end = min(query_end, valid_until) if valid_until else query_end

    if effective_start > effective_end:
        return []

    # Jump to the first matching weekday on or after effective_start
    days_ahead = (target_weekday - effective_start.weekday()) % 7
    current = effective_start + timedelta(days=days_ahead)

    intervals: list[Interval] = []
    while current <= effective_end:
        intervals.append(
            (
                datetime.combine(current, start_time, tzinfo=IST),
                datetime.combine(current, end_time, tzinfo=IST),
            )
        )
        current += timedelta(days=7)

    return intervals


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """
    Merge overlapping or adjacent intervals into non-overlapping intervals.

    Input:  [(9:00, 12:00), (11:00, 14:00), (15:00, 17:00)]
    Output: [(9:00, 14:00), (15:00, 17:00)]
    """
    if not intervals:
        return []

    sorted_iv = sorted(intervals)
    merged = [sorted_iv[0]]

    for start, end in sorted_iv[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def intersect_intervals(
    a: list[Interval],
    b: list[Interval],
) -> list[Interval]:
    """
    Compute the intersection of two sorted, non-overlapping interval lists.

    a = [(9:00, 12:00), (13:00, 17:00)]   # Room available
    b = [(10:00, 15:00)]                    # Associate available
    → [(10:00, 12:00), (13:00, 15:00)]     # Both available
    """
    result: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if start < end:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def intersect_many(*interval_lists: list[Interval]) -> list[Interval]:
    """
    Intersect multiple interval lists.

    Returns the intervals where ALL resources are simultaneously available.
    Each input list must be sorted and non-overlapping.
    """
    if not interval_lists:
        return []

    result = interval_lists[0]
    for other in interval_lists[1:]:
        result = intersect_intervals(result, other)
        if not result:
            return []
    return result


def subtract_intervals(
    available: list[Interval],
    busy: list[Interval],
) -> list[Interval]:
    """
    Remove busy intervals from available intervals. Both lists must be sorted.

    available = [(9:00, 17:00)]
    busy = [(11:00, 12:00), (14:00, 15:00)]
    → [(9:00, 11:00), (12:00, 14:00), (15:00, 17:00)]
    """
    result: list[Interval] = []
    b_idx = 0

    for avail_start, avail_end in available:
        current = avail_start

        while b_idx < len(busy) and busy[b_idx][1] <= current:
            b_idx += 1

        bi = b_idx
        while bi < len(busy) and busy[bi][0] < avail_end:
            busy_start, busy_end = busy[bi]
            if busy_start > current:
                result.append((current, min(busy_start, avail_end)))
            current = max(current, busy_end)
            bi += 1

        if current < avail_end:
            result.append((current, avail_end))

    return result


def split_into_slots(
    intervals: list[Interval],
    duration_minutes: int,
    buffer_minutes: int = 0,
) -> list[Interval]:
    """
    Split free intervals into fixed-duration bookable slots.

    intervals = [(9:00, 12:00)]
    duration = 30 min, buffer = 10 min
    → [(9:00, 9:30), (9:40, 10:10), (10:20, 10:50), (11:00, 11:30)]

    Buffer time is added AFTER each slot to prevent back-to-back bookings.
    The last slot in an interval doesn't need trailing buffer space.
    """
    slots: list[Interval] = []
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=duration_minutes + buffer_minutes)

    for start, end in intervals:
        slot_start = start
        while slot_start + duration <= end:
            slots.append((slot_start, slot_start + duration))
            slot_start += step

    return slots
