from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts.users.models import User
from integrations.google_calendar.db import persist_google_calendar_connection
from integrations.google_calendar.tokens import get_valid_access_token
from integrations.google_calendar.views import complete_google_calendar_connection
from integrations.models import GoogleCalendarConnection


def invalid_grant_http_error():
    response = MagicMock()
    response.status_code = 400
    response.json.return_value = {"error": "invalid_grant"}
    error = requests.HTTPError("invalid_grant")
    error.response = response
    return error


class GoogleCalendarTokenRefreshTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="calendar-owner@example.com")
        self.expired_at = timezone.now() - timedelta(minutes=1)
        self.connection = GoogleCalendarConnection.objects.create(
            user=self.user,
            google_email="care@biopeak.health",
            google_access_token="enc:access-a",
            google_refresh_token="enc:refresh-a",
            google_access_token_expires_at=self.expired_at,
        )

    @patch("integrations.google_calendar.tokens.decrypt", side_effect=lambda value: value)
    @patch("integrations.google_calendar.tokens.google_oauth.refresh_access_token")
    def test_invalid_grant_deactivates_when_refresh_token_unchanged(
        self, mock_refresh, _mock_decrypt
    ):
        mock_refresh.side_effect = invalid_grant_http_error()
        with self.assertRaises(requests.HTTPError):
            get_valid_access_token(self.connection)
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.is_active)
        self.assertEqual(self.connection.google_refresh_token, "enc:refresh-a")
        self.assertEqual(self.connection.google_access_token, "enc:access-a")
        self.assertEqual(
            self.connection.google_access_token_expires_at, self.expired_at
        )

    @patch("integrations.google_calendar.tokens.decrypt", side_effect=lambda value: value)
    @patch("integrations.google_calendar.tokens.google_oauth.refresh_access_token")
    def test_invalid_grant_retries_when_refresh_token_rotated(
        self, mock_refresh, mock_decrypt
    ):
        def rotate_then_reject(_refresh_token):
            GoogleCalendarConnection.objects.filter(pk=self.connection.pk).update(
                google_refresh_token="enc:refresh-b",
                google_access_token="enc:access-b",
                google_access_token_expires_at=timezone.now() + timedelta(hours=1),
            )
            raise invalid_grant_http_error()

        mock_refresh.side_effect = rotate_then_reject
        access_token = get_valid_access_token(self.connection)
        self.assertEqual(access_token, "enc:access-b")
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.google_refresh_token, "enc:refresh-b")
        mock_decrypt.assert_called()


class GoogleCalendarCompletePersistTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.stale_user = User.objects.create_user(email="stale@example.com")
        self.expires_at = timezone.now() + timedelta(hours=1)

    def test_persist_evicts_stale_email_holder(self):
        GoogleCalendarConnection.objects.create(
            user=self.stale_user,
            google_email="care@biopeak.health",
            google_refresh_token="enc:old",
        )
        stale_count = persist_google_calendar_connection(
            self.owner,
            "care@biopeak.health",
            "enc:new-access",
            "enc:new-refresh",
            self.expires_at,
        )
        self.assertEqual(stale_count, 1)
        stale = GoogleCalendarConnection.objects.filter(pk=self.stale_user.pk).first()
        self.assertIsNone(stale.google_email)
        self.assertIsNone(stale.google_refresh_token)
        owner = GoogleCalendarConnection.objects.filter(pk=self.owner.pk).first()
        self.assertEqual(owner.google_email, "care@biopeak.health")
        self.assertEqual(owner.google_refresh_token, "enc:new-refresh")

    @patch("integrations.google_calendar.views.persist_google_calendar_connection")
    def test_complete_reuses_row_when_unique_race_already_connected(
        self, mock_persist
    ):
        mock_persist.side_effect = IntegrityError(
            "uniq_google_calendar_connection_email"
        )
        GoogleCalendarConnection.objects.create(
            user=self.owner,
            google_email="care@biopeak.health",
            google_refresh_token="enc:live",
            is_active=True,
        )
        stale_count = complete_google_calendar_connection(
            self.owner,
            "care@biopeak.health",
            "enc:access",
            "enc:refresh",
            self.expires_at,
        )
        self.assertEqual(stale_count, 0)
        mock_persist.assert_called_once()

    @patch("integrations.google_calendar.views.persist_google_calendar_connection")
    def test_complete_retries_unique_race_then_persists(self, mock_persist):
        mock_persist.side_effect = [
            IntegrityError("uniq_google_calendar_connection_email"),
            1,
        ]
        stale_count = complete_google_calendar_connection(
            self.owner,
            "care@biopeak.health",
            "enc:access",
            "enc:refresh",
            self.expires_at,
        )
        self.assertEqual(stale_count, 1)
        self.assertEqual(mock_persist.call_count, 2)
