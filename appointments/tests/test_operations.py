from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import QueryDict
from django.test import TestCase

from appointments.tests.test_booking_lifecycle import (
    BookingWorldTests,
    book_appointment,
    cancel_appointment,
    find_slots,
    first_slot,
)
from appointments.utils.constants import AppointmentStatus
from appointments.utils.operations import (
    aggregate_booked_metrics,
    build_associate_capacity,
    parse_operations_date_range,
)


class OperationsDateRangeTests(TestCase):
    def test_malformed_start_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            parse_operations_date_range(QueryDict("start=not-a-date"))
        self.assertIn("Invalid start date.", raised.exception.messages[0])

    def test_impossible_calendar_date_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            parse_operations_date_range(QueryDict("start=2026-02-29"))
        self.assertIn("Invalid start date.", raised.exception.messages[0])

    def test_junk_granularity_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            parse_operations_date_range(QueryDict("granularity=fortnight"))
        self.assertIn("Invalid granularity.", raised.exception.messages[0])

    def test_end_before_start_raises(self):
        with self.assertRaises(DjangoValidationError) as raised:
            parse_operations_date_range(QueryDict("start=2026-09-20&end=2026-09-19"))
        self.assertIn("End date cannot be before start date.", raised.exception.messages[0])

    def test_valid_explicit_range(self):
        start_date, end_date = parse_operations_date_range(
            QueryDict("start=2026-09-21&end=2026-09-27")
        )
        self.assertEqual(start_date, date(2026, 9, 21))
        self.assertEqual(end_date, date(2026, 9, 27))


class OperationsBusyMetricsTests(BookingWorldTests):
    def test_cancelled_appointments_are_excluded_from_booked_metrics(self):
        first_slots = find_slots(self.center, self.virtual_slot_payload())
        first_appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(first_slot(first_slots))
        )
        second_slots = find_slots(self.center, self.virtual_slot_payload())
        second_appointment = book_appointment(
            self.center, self.actor, self.book_virtual_payload(first_slot(second_slots))
        )
        cancel_appointment(first_appointment, self.actor)
        slot_date = first_appointment.start_datetime.astimezone().date()
        metrics = aggregate_booked_metrics(self.center, slot_date, slot_date)
        self.assertEqual(metrics["appointment_count"], 1)
        self.assertEqual(metrics["booked_minutes"], second_appointment.duration_minutes)
        self.assertEqual(metrics["status_breakdown"], {AppointmentStatus.CONFIRMED: 1})
        staff_row = build_associate_capacity(
            self.center, self.coach, slot_date, slot_date
        )
        self.assertEqual(staff_row["booked_minutes"], second_appointment.duration_minutes)
        self.assertNotIn(AppointmentStatus.CANCELLED, metrics["status_breakdown"])
