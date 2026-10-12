from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from wearables.services.analytics import (
    connection_priority_state,
    current_value_payload,
    history_window_availability,
)
from wearables.utils.constants import HealthDomain, PreferredUnits


class AnalyticsAvailabilityTests(TestCase):
    def test_no_connections_is_not_reported_as_disconnected(self):
        self.assertIsNone(connection_priority_state([]))

    def test_history_windows_use_prd_observation_thresholds(self):
        summaries = [object()] * 60

        availability = history_window_availability(summaries)

        self.assertTrue(availability["7d"]["available"])
        self.assertTrue(availability["30d"]["available"])
        self.assertTrue(availability["90d"]["available"])
        self.assertEqual(availability["30d"]["requiredObservationDays"], 21)
        self.assertEqual(availability["90d"]["requiredObservationDays"], 60)

    def test_missing_workout_values_are_not_converted_to_zero(self):
        summary = SimpleNamespace(
            metric="workout_count",
            total=None,
            local_date=date(2026, 10, 8),
            last_observed_at=None,
        )

        current_value = current_value_payload(
            summaries=[summary],
            metric="workout_count",
            preferred_units=PreferredUnits.METRIC,
            domain=HealthDomain.WORKOUTS,
        )

        self.assertEqual(current_value, {"available": False})
