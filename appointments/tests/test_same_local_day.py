from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from appointments.utils.overlap import (
    day_window_utc,
    validate_same_day_time_window,
)

KOLKATA = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")
SAME_DAY_TIME_ERROR = "Must be after start_time on the same day."


class SameDayTimeWindowTests(SimpleTestCase):
    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_day_window_utc_combines_local_date_and_times(self):
        start_utc, end_utc = day_window_utc(
            date(2026, 9, 3), time(8, 0), time(18, 0)
        )
        self.assertEqual(
            start_utc,
            datetime(2026, 9, 3, 8, 0, tzinfo=KOLKATA).astimezone(UTC),
        )
        self.assertEqual(
            end_utc,
            datetime(2026, 9, 3, 18, 0, tzinfo=KOLKATA).astimezone(UTC),
        )

    def test_validate_same_day_time_window_rejects_end_before_start(self):
        errors = {}
        validate_same_day_time_window(time(18, 0), time(8, 0), errors)
        self.assertEqual(errors["end_time"], [SAME_DAY_TIME_ERROR])

    def test_validate_same_day_time_window_accepts_valid_range(self):
        errors = {}
        validate_same_day_time_window(time(8, 0), time(18, 0), errors)
        self.assertEqual(errors, {})
