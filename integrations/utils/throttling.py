"""Rate limits for public integrations endpoints."""

from rest_framework.throttling import AnonRateThrottle

from core.utils.helper import get_request_ip_address


class AppDownloadThrottle(AnonRateThrottle):
    scope = "app_download"

    def get_ident(self, request):
        return get_request_ip_address(request) or "unknown"
