from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase
from django.utils import timezone

from accounts.users.models import User
from integrations.google_calendar.tokens import get_valid_access_token
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
    def test_invalid_grant_clears_when_refresh_token_unchanged(
        self, mock_refresh, _mock_decrypt
    ):
        mock_refresh.side_effect = invalid_grant_http_error()
        with self.assertRaises(requests.HTTPError):
            get_valid_access_token(self.connection)
        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.google_refresh_token)
        self.assertIsNone(self.connection.google_access_token)
        self.assertIsNone(self.connection.google_access_token_expires_at)

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
