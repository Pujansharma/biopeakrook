from types import SimpleNamespace
from unittest import TestCase

from wearables.services.notifications import (
    apply_notification_state,
    notification_data_source,
    notification_text,
)
from wearables.utils.constants import (
    AuthorizationStatus,
    ConnectionStatus,
    HistoricalImportStatus,
)


class NotificationNormalizationTests(TestCase):
    def test_authorization_completed_event_activates_connection(self):
        connection = SimpleNamespace(
            status=ConnectionStatus.AUTHORIZING,
            authorization_status=AuthorizationStatus.PENDING,
            import_status=HistoricalImportStatus.NOT_STARTED,
            connected_at=None,
        )

        text = notification_text({"event_type": "authorization_completed"})
        apply_notification_state(connection, text)

        self.assertEqual(connection.status, ConnectionStatus.ACTIVE)
        self.assertEqual(
            connection.authorization_status,
            AuthorizationStatus.AUTHORIZED,
        )

    def test_provider_name_is_canonicalized(self):
        self.assertEqual(
            notification_data_source({"data_source": "garmin"}),
            "Garmin",
        )
