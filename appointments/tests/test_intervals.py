from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from appointments.utils.intervals import (
    intersect_intervals,
    merge_intervals,
    resolve_query_date_range,
    subtract_intervals,
)


class IntervalLogicTests(SimpleTestCase):
    def test_merge_intervals_combines_overlaps(self):
        first = (
            datetime(2026, 8, 26, 9, 0, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 8, 26, 12, 0, tzinfo=ZoneInfo("UTC")),
        )
        second = (
            datetime(2026, 8, 26, 11, 0, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 8, 26, 14, 0, tzinfo=ZoneInfo("UTC")),
        )
        merged = merge_intervals([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][0], first[0])
        self.assertEqual(merged[0][1], second[1])

    def test_subtract_intervals_removes_busy_window(self):
        available = [
            (
                datetime(2026, 8, 26, 9, 0, tzinfo=ZoneInfo("UTC")),
                datetime(2026, 8, 26, 17, 0, tzinfo=ZoneInfo("UTC")),
            )
        ]
        busy = [
            (
                datetime(2026, 8, 26, 12, 0, tzinfo=ZoneInfo("UTC")),
                datetime(2026, 8, 26, 13, 0, tzinfo=ZoneInfo("UTC")),
            )
        ]
        free = subtract_intervals(available, busy)
        self.assertEqual(len(free), 2)
        self.assertEqual(free[0][1], busy[0][0])
        self.assertEqual(free[1][0], busy[0][1])

    def test_intersect_intervals_finds_overlap(self):
        first = [
            (
                datetime(2026, 8, 26, 9, 0, tzinfo=ZoneInfo("UTC")),
                datetime(2026, 8, 26, 13, 0, tzinfo=ZoneInfo("UTC")),
            )
        ]
        second = [
            (
                datetime(2026, 8, 26, 11, 0, tzinfo=ZoneInfo("UTC")),
                datetime(2026, 8, 26, 15, 0, tzinfo=ZoneInfo("UTC")),
            )
        ]
        overlap = intersect_intervals(first, second)
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0][0].hour, 11)
        self.assertEqual(overlap[0][1].hour, 13)

    def test_resolve_query_date_range_week(self):
        start = date(2026, 8, 26)
        week_start, week_end = resolve_query_date_range(start, "week")
        self.assertEqual(week_start, date(2026, 8, 24))
        self.assertEqual(week_end, date(2026, 8, 30))
