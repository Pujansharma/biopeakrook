from datetime import timedelta
from unittest.mock import patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from accounts.users.models import User
from integrations.google_calendar.views import GoogleCalendarWebhookView
from integrations.google_calendar.webhook_channel import (
    ensure_watch_channel_active,
    find_connection_for_watch_channel,
    personal_connections_needing_watch_renewal,
    start_watch_channel,
    stop_watch_channel,
    watch_channel_expires_soon,
)
from integrations.models import GoogleCalendarConnection


def create_connection(email="staff@example.com", **overrides):
    user = User.objects.create_user(email=email)
    fields = {
        "google_refresh_token": "enc:refresh",
        "google_access_token": "enc:access",
        "google_access_token_expires_at": timezone.now() + timedelta(hours=1),
    }
    fields.update(overrides)
    return GoogleCalendarConnection.objects.create(user=user, **fields)


class WatchChannelExpiryTests(TestCase):
    def test_expires_soon_when_never_registered(self):
        connection = create_connection()
        self.assertTrue(watch_channel_expires_soon(connection))

    def test_expires_soon_within_threshold(self):
        connection = create_connection(
            watch_channel_id="chan-1",
            watch_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(watch_channel_expires_soon(connection))

    def test_not_expiring_soon(self):
        connection = create_connection(
            watch_channel_id="chan-1",
            watch_expires_at=timezone.now() + timedelta(days=5),
        )
        self.assertFalse(watch_channel_expires_soon(connection))


class FindConnectionForWatchChannelTests(TestCase):
    def test_matches_active_connection(self):
        connection = create_connection(
            watch_channel_id="chan-1", watch_resource_id="res-1",
        )
        found = find_connection_for_watch_channel("chan-1", "res-1")
        self.assertEqual(found.pk, connection.pk)

    def test_ignores_inactive_connection(self):
        create_connection(
            watch_channel_id="chan-1", watch_resource_id="res-1", is_active=False,
        )
        self.assertIsNone(find_connection_for_watch_channel("chan-1", "res-1"))

    def test_no_match_returns_none(self):
        self.assertIsNone(find_connection_for_watch_channel(None, None))
        self.assertIsNone(find_connection_for_watch_channel("chan-1", "res-1"))


class StartAndStopWatchChannelTests(TestCase):
    def setUp(self):
        self.connection = create_connection()

    @patch("integrations.google_calendar.webhook_channel.get_valid_access_token")
    @patch("integrations.google_calendar.webhook_channel.calendar_api.watch_events")
    def test_start_persists_googles_response(self, mock_watch, mock_token):
        mock_token.return_value = "access-token"
        expiration_ms = int((timezone.now() + timedelta(days=7)).timestamp() * 1000)
        mock_watch.return_value = {"resourceId": "res-xyz", "expiration": str(expiration_ms)}

        start_watch_channel(self.connection)

        self.connection.refresh_from_db()
        self.assertTrue(self.connection.watch_channel_id)
        self.assertEqual(self.connection.watch_resource_id, "res-xyz")
        self.assertIsNotNone(self.connection.watch_expires_at)

    @patch("integrations.google_calendar.webhook_channel.get_valid_access_token")
    @patch("integrations.google_calendar.webhook_channel.calendar_api.stop_channel")
    def test_stop_clears_fields_and_calls_google(self, mock_stop, mock_token):
        self.connection.watch_channel_id = "chan-1"
        self.connection.watch_resource_id = "res-1"
        self.connection.watch_expires_at = timezone.now() + timedelta(days=1)
        self.connection.save()
        mock_token.return_value = "access-token"

        stop_watch_channel(self.connection)

        mock_stop.assert_called_once_with("access-token", "chan-1", "res-1")
        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.watch_channel_id)
        self.assertIsNone(self.connection.watch_resource_id)
        self.assertIsNone(self.connection.watch_expires_at)

    @patch("integrations.google_calendar.webhook_channel.get_valid_access_token")
    @patch("integrations.google_calendar.webhook_channel.calendar_api.stop_channel")
    def test_stop_still_clears_fields_when_google_call_fails(self, mock_stop, mock_token):
        self.connection.watch_channel_id = "chan-1"
        self.connection.watch_resource_id = "res-1"
        self.connection.save()
        mock_token.return_value = "access-token"
        mock_stop.side_effect = requests.RequestException("boom")

        stop_watch_channel(self.connection)

        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.watch_channel_id)

    def test_stop_is_a_noop_without_an_existing_channel(self):
        stop_watch_channel(self.connection)  # must not raise


class EnsureWatchChannelActiveTests(TestCase):
    def setUp(self):
        self.connection = create_connection()

    @patch("integrations.google_calendar.webhook_channel.start_watch_channel")
    def test_registers_when_missing(self, mock_start):
        ensure_watch_channel_active(self.connection)
        mock_start.assert_called_once_with(self.connection)

    @patch("integrations.google_calendar.webhook_channel.start_watch_channel")
    def test_noop_when_not_expiring_soon(self, mock_start):
        self.connection.watch_channel_id = "chan-1"
        self.connection.watch_expires_at = timezone.now() + timedelta(days=5)
        self.connection.save()

        ensure_watch_channel_active(self.connection)

        mock_start.assert_not_called()

    @patch("integrations.google_calendar.webhook_channel.stop_channel_at_google")
    @patch("integrations.google_calendar.webhook_channel.start_watch_channel")
    def test_replaces_an_expiring_channel_starting_new_before_stopping_old(
        self, mock_start, mock_stop
    ):
        self.connection.watch_channel_id = "chan-1"
        self.connection.watch_resource_id = "res-1"
        self.connection.watch_expires_at = timezone.now() - timedelta(hours=1)
        self.connection.save()
        calls = []
        mock_start.side_effect = lambda connection: calls.append("start")
        mock_stop.side_effect = lambda *args: calls.append("stop")

        ensure_watch_channel_active(self.connection)

        self.assertEqual(calls, ["start", "stop"])
        mock_stop.assert_called_once_with(self.connection, "chan-1", "res-1")

    @override_settings(GOOGLE_CALENDAR_ID="care@biopeak.health")
    @patch("integrations.google_calendar.webhook_channel.start_watch_channel")
    def test_shared_organizer_is_never_watched(self, mock_start):
        self.connection.google_email = "care@biopeak.health"
        self.connection.save()

        ensure_watch_channel_active(self.connection)

        mock_start.assert_not_called()

    @patch("integrations.google_calendar.webhook_channel.stop_channel_at_google")
    @patch("integrations.google_calendar.webhook_channel.start_watch_channel")
    def test_keeps_old_channel_when_starting_new_one_fails(self, mock_start, mock_stop):
        self.connection.watch_channel_id = "chan-1"
        self.connection.watch_resource_id = "res-1"
        self.connection.watch_expires_at = timezone.now() - timedelta(hours=1)
        self.connection.save()
        mock_start.side_effect = requests.RequestException("boom")

        with self.assertRaises(requests.RequestException):
            ensure_watch_channel_active(self.connection)

        mock_stop.assert_not_called()
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.watch_channel_id, "chan-1")


class PersonalConnectionsNeedingRenewalTests(TestCase):
    def renewal_pks(self):
        return {c.pk for c in personal_connections_needing_watch_renewal()}

    def test_includes_connected_rows_with_no_channel(self):
        connection = create_connection(email="nochannel@example.com")
        self.assertIn(connection.pk, self.renewal_pks())

    def test_includes_channel_without_expiry(self):
        connection = create_connection(
            email="noexpiry@example.com", watch_channel_id="chan-1"
        )
        self.assertIn(connection.pk, self.renewal_pks())

    def test_includes_expiring_channel_and_skips_healthy_one(self):
        expiring = create_connection(
            email="expiring@example.com",
            watch_channel_id="chan-1",
            watch_expires_at=timezone.now() + timedelta(hours=1),
        )
        healthy = create_connection(
            email="healthy@example.com",
            watch_channel_id="chan-2",
            watch_expires_at=timezone.now() + timedelta(days=10),
        )
        self.assertIn(expiring.pk, self.renewal_pks())
        self.assertNotIn(healthy.pk, self.renewal_pks())

    def test_skips_disconnected_rows(self):
        connection = create_connection(email="off@example.com", is_active=False)
        self.assertNotIn(connection.pk, self.renewal_pks())


class GoogleCalendarWebhookViewTests(TestCase):
    def setUp(self):
        self.connection = create_connection(
            watch_channel_id="chan-1",
            watch_resource_id="res-1",
        )

    def post_webhook(self, resource_state, channel_id="chan-1", resource_id="res-1"):
        factory = APIRequestFactory()
        request = factory.post(
            "/google-calendar/webhook/",
            HTTP_X_GOOG_CHANNEL_ID=channel_id,
            HTTP_X_GOOG_RESOURCE_ID=resource_id,
            HTTP_X_GOOG_RESOURCE_STATE=resource_state,
        )
        return GoogleCalendarWebhookView.as_view()(request)

    @patch("integrations.google_calendar.views.sync_google_events_to_availability_blocks")
    def test_change_notification_triggers_sync(self, mock_sync):
        response = self.post_webhook("exists")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_once_with(self.connection.user, self.connection)

    @patch("integrations.google_calendar.views.sync_google_events_to_availability_blocks")
    def test_initial_sync_handshake_does_not_trigger_a_sync(self, mock_sync):
        response = self.post_webhook("sync")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_not_called()

    @patch("integrations.google_calendar.views.sync_google_events_to_availability_blocks")
    def test_unknown_channel_is_ignored(self, mock_sync):
        response = self.post_webhook("exists", channel_id="unknown", resource_id="unknown")
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_not_called()

    @patch("integrations.google_calendar.views.sync_google_events_to_availability_blocks")
    def test_google_sync_failure_is_swallowed(self, mock_sync):
        mock_sync.side_effect = requests.RequestException("boom")
        response = self.post_webhook("exists")
        self.assertEqual(response.status_code, 200)
