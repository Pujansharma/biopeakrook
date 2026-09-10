from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from appointments.models import Appointment
from appointments.utils.constants import AvailabilityGranularity
from appointments.views.booking import (
    apply_appointment_list_filters,
    appointment_list_applies_hard_cap,
    appointment_list_uses_date_window,
    parse_optional_uuid_query,
)


class AppointmentListQueryHelperTests(SimpleTestCase):
    def test_search_without_start_skips_date_window(self):
        params = QueryDict("search=Meera")
        self.assertFalse(appointment_list_uses_date_window(params))

    def test_search_with_start_uses_date_window(self):
        params = QueryDict("search=Meera&start=2026-09-01")
        self.assertTrue(appointment_list_uses_date_window(params))

    def test_no_search_uses_date_window(self):
        params = QueryDict("start=2026-09-01&granularity=week")
        self.assertTrue(appointment_list_uses_date_window(params))

    def test_unscoped_search_applies_hard_cap(self):
        params = QueryDict("search=Meera")
        self.assertTrue(appointment_list_applies_hard_cap(params))

    def test_week_window_applies_hard_cap(self):
        params = QueryDict(f"start=2026-09-01&granularity={AvailabilityGranularity.WEEK}")
        self.assertTrue(appointment_list_applies_hard_cap(params))

    def test_day_window_skips_hard_cap(self):
        params = QueryDict(f"start=2026-09-01&granularity={AvailabilityGranularity.DAY}")
        self.assertFalse(appointment_list_applies_hard_cap(params))

    def test_junk_uuid_rejected(self):
        params = QueryDict("associate_id=not-a-uuid")
        value, error = parse_optional_uuid_query(params, "associate_id")
        self.assertIsNone(value)
        self.assertEqual(error, "Invalid associate_id.")

    def test_blank_uuid_omitted(self):
        params = QueryDict("associate_id=")
        value, error = parse_optional_uuid_query(params, "associate_id")
        self.assertIsNone(value)
        self.assertIsNone(error)


class AppointmentListStaffFilterTests(TestCase):
    def test_associate_and_role_combine_with_or(self):
        associate_id = "11111111-1111-1111-1111-111111111111"
        role_id = "22222222-2222-2222-2222-222222222222"
        params = QueryDict(f"associate_id={associate_id}&role_id={role_id}")
        queryset, error = apply_appointment_list_filters(
            Appointment.objects.all(),
            params,
        )
        self.assertIsNone(error)
        sql = str(queryset.query).upper()
        self.assertIn(" OR ", sql)
        self.assertIn("ASSOCIATE_ID", sql)
        self.assertIn("ROLE_ID", sql)

    def test_invalid_status_rejected(self):
        params = QueryDict("status=pending")
        queryset, error = apply_appointment_list_filters(
            Appointment.objects.all(),
            params,
        )
        self.assertIsNone(queryset)
        self.assertIn("Invalid status", error)
