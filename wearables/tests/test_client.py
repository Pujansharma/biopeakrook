from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings

from wearables.services.client import (
    RookClient,
    RookServiceError,
    authorized_source_names,
    validate_authorization_url,
)


class RookClientContractTests(TestCase):
    def test_authorized_sources_uses_only_true_rows(self):
        sources = authorized_source_names(
            {
                "data_sources": [
                    {"data_source": "Garmin", "authorized": True},
                    {"data_source": "Oura", "authorized": False},
                ]
            }
        )

        self.assertEqual(sources, {"Garmin"})

    def test_garmin_url_requires_trusted_https_host(self):
        self.assertEqual(
            validate_authorization_url(
                "Garmin",
                "https://connect.garmin.com/oauthConfirm",
            ),
            "https://connect.garmin.com/oauthConfirm",
        )
        with self.assertRaises(RookServiceError):
            validate_authorization_url(
                "Garmin",
                "https://malicious.example/oauthConfirm",
            )

    @override_settings(
        ROOK_BASE_URL="https://api.rook-connect.review",
        ROOK_CLIENT_UUID="client-one",
        ROOK_SECRET_KEY="server-secret",
    )
    @patch("wearables.services.client.requests.request")
    def test_revoke_uses_rook_singular_data_source_endpoint(self, request_mock):
        request_mock.return_value = SimpleNamespace(
            status_code=204,
            content=b"",
        )

        RookClient().revoke_source(
            rook_user_id="member-one",
            data_source="Garmin",
        )

        expected_url = (
            "https://api.rook-connect.review/api/v1/user_id/"
            "member-one/data_source/revoke_auth"
        )
        self.assertEqual(
            request_mock.call_args.args[:2],
            ("POST", expected_url),
        )
        self.assertEqual(
            request_mock.call_args.kwargs["json"],
            {"data_source": "Garmin"},
        )

