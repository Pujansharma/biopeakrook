from unittest import TestCase

from wearables.services.metrics import extract_metric_values
from wearables.services.provenance import extract_provenance
from wearables.utils.constants import HealthDomain


class MetricExtractionTests(TestCase):
    def test_extracts_canonical_sleep_duration_in_seconds(self):
        metrics = list(
            extract_metric_values(
                {"sleep_duration_hours": 7.5},
                data_structure="sleep_health_summary",
            )
        )

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].domain, HealthDomain.SLEEP)
        self.assertEqual(metrics[0].metric, "sleep_duration_seconds")
        self.assertEqual(metrics[0].value, 27000.0)
        self.assertEqual(metrics[0].unit, "seconds")

    def test_extracts_steps_without_exposing_private_identifiers(self):
        metrics = list(
            extract_metric_values(
                {
                    "user_id": "private-user",
                    "document_version": 2,
                    "accumulated_steps_int": 9234,
                },
                data_structure="physical_health_summary",
            )
        )

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].domain, HealthDomain.ACTIVITY)
        self.assertEqual(metrics[0].metric, "steps")
        self.assertEqual(metrics[0].value, 9234.0)


class ProvenanceTests(TestCase):
    def test_preserves_multi_source_and_device_metadata(self):
        provenance = extract_provenance(
            {
                "source_of_data_string": "Garmin",
                "nested": {
                    "sources_of_data_array": ["Oura"],
                    "device_source_data_array": [
                        {"manufacturer_string": "Example", "model_string": "One"}
                    ],
                },
            }
        )

        self.assertEqual(provenance["data_sources"], ["Garmin", "Oura"])
        self.assertTrue(provenance["multi_source"])
        self.assertEqual(len(provenance["device_metadata"]), 1)

