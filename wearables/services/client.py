import base64
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings

from core.utils.log import logger


class RookConfigurationError(RuntimeError):
    pass


class RookServiceError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def authorized_source_names(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    sources = payload.get("data_sources")
    if not isinstance(sources, list):
        return set()
    return {
        str(source.get("data_source"))
        for source in sources
        if isinstance(source, dict)
        and source.get("authorized") is True
        and source.get("data_source")
    }


def validate_authorization_url(data_source: str, value: Any) -> str | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise RookServiceError("ROOK returned an invalid authorization URL.")
    try:
        parsed = urlparse(value)
        invalid_port = parsed.port is not None
    except ValueError as error:
        raise RookServiceError(
            "ROOK returned an invalid authorization URL."
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or invalid_port
    ):
        raise RookServiceError("ROOK returned an unsafe authorization URL.")
    if data_source == "Garmin":
        if parsed.hostname != "connect.garmin.com":
            raise RookServiceError("ROOK returned an untrusted Garmin URL.")
        return value
    configured_hosts = getattr(settings, "ROOK_AUTHORIZATION_ALLOWED_HOSTS", [])
    if configured_hosts and parsed.hostname not in configured_hosts:
        raise RookServiceError("ROOK returned an untrusted authorization host.")
    return value


class RookClient:
    def __init__(self):
        self.base_url = getattr(settings, "ROOK_BASE_URL", "").rstrip("/")
        self.client_uuid = getattr(settings, "ROOK_CLIENT_UUID", "")
        self.secret_key = getattr(settings, "ROOK_SECRET_KEY", "")
        self.connect_timeout = getattr(settings, "ROOK_CONNECT_TIMEOUT_SECONDS", 5)
        self.read_timeout = getattr(settings, "ROOK_READ_TIMEOUT_SECONDS", 12)

    def ensure_configured(self) -> None:
        if not self.base_url or not self.client_uuid or not self.secret_key:
            raise RookConfigurationError("ROOK credentials are not configured.")

    def authentication_headers(self) -> dict[str, str]:
        self.ensure_configured()
        credentials = base64.b64encode(
            f"{self.client_uuid}:{self.secret_key}".encode()
        ).decode("ascii")
        return {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }

    def request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        parameters: dict | None = None,
    ) -> dict:
        try:
            response = requests.request(
                method,
                url,
                headers=self.authentication_headers(),
                json=json_body,
                params=parameters,
                timeout=(self.connect_timeout, self.read_timeout),
            )
        except requests.RequestException as error:
            raise RookServiceError(
                "ROOK could not be reached. Please retry."
            ) from error
        if response.status_code >= 400:
            logger.warning(
                f"ROOK request failed with HTTP {response.status_code} for {method} {url}"
            )
            raise RookServiceError(
                f"ROOK request failed with HTTP {response.status_code}."
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as error:
            raise RookServiceError("ROOK returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise RookServiceError("ROOK returned an invalid response.")
        return payload

    def get_processed_summaries(
        self,
        *,
        rook_user_id: str,
        health_pillar: str,
        summary_date: str,
    ) -> list[dict]:
        url = f"{self.base_url}/v2/processed_data/{health_pillar}_health/summary"
        try:
            response = requests.get(
                url,
                headers=self.authentication_headers(),
                params={"user_id": rook_user_id, "date": summary_date},
                timeout=(self.connect_timeout, self.read_timeout),
            )
        except requests.RequestException as error:
            raise RookServiceError(
                "ROOK recovery data could not be reached."
            ) from error
        if response.status_code == 204 or not response.content:
            return []
        if response.status_code >= 400:
            raise RookServiceError(
                f"ROOK recovery request failed with HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise RookServiceError("ROOK returned invalid recovery JSON.") from error
        documents = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(document, dict) for document in documents):
            raise RookServiceError("ROOK returned invalid recovery documents.")
        return documents

    def get_authorizer(
        self,
        *,
        rook_user_id: str,
        data_source: str,
        redirect_url: str | None = None,
    ) -> dict:
        url = (
            f"{self.base_url}/api/v1/user_id/{rook_user_id}/"
            f"data_source/{data_source}/authorizer"
        )
        parameters = {"redirect_url": redirect_url} if redirect_url else None
        payload = self.request_json("GET", url, parameters=parameters)
        authorization_url = validate_authorization_url(
            data_source,
            payload.get("authorization_url") or payload.get("authorizer_url"),
        )
        return {
            "data_source": data_source,
            "authorized": payload.get("authorized") is True,
            "authorization_url": authorization_url,
        }

    def get_authorized_sources(self, *, rook_user_id: str) -> set[str]:
        url = (
            f"{self.base_url}/api/v2/user_id/{rook_user_id}/"
            "data_sources/authorized"
        )
        return authorized_source_names(self.request_json("GET", url))

    def revoke_source(self, *, rook_user_id: str, data_source: str) -> None:
        url = (
            f"{self.base_url}/api/v1/user_id/{rook_user_id}/"
            "data_source/revoke_auth"
        )
        self.request_json("POST", url, json_body={"data_source": data_source})

