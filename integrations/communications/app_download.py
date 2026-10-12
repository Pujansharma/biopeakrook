import logging
import re
from urllib.parse import urlencode

from django.db import DatabaseError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.utils.helper import get_request_ip_address, get_request_user_agent
from integrations.models import AppDownloadClick
from integrations.utils.constants import (
    APP_DOWNLOAD_BOT_USER_AGENT_PATTERN,
    APP_DOWNLOAD_CHOOSER_TEMPLATE,
    APP_DOWNLOAD_DESTINATION_BY_PLATFORM,
    APP_DOWNLOAD_USER_AGENT_MAX_LENGTH,
    AppDownloadEntry,
    AppDownloadPlatform,
)
from integrations.utils.throttling import AppDownloadThrottle

logger = logging.getLogger(__name__)

FORCED_APP_DOWNLOAD_PLATFORMS = frozenset(
    {
        AppDownloadPlatform.ANDROID,
        AppDownloadPlatform.IOS,
    }
)

APP_DOWNLOAD_BOT_USER_AGENT_REGEX = re.compile(
    APP_DOWNLOAD_BOT_USER_AGENT_PATTERN,
    re.IGNORECASE,
)


def detect_app_download_platform(user_agent):
    if not user_agent:
        return AppDownloadPlatform.OTHER
    lower_user_agent = user_agent.lower()
    if "android" in lower_user_agent:
        return AppDownloadPlatform.ANDROID
    if (
        "iphone" in lower_user_agent
        or "ipad" in lower_user_agent
        or "ipod" in lower_user_agent
    ):
        return AppDownloadPlatform.IOS
    # iPadOS 13+ Safari often reports as Macintosh + Mobile.
    if "macintosh" in lower_user_agent and "mobile" in lower_user_agent:
        return AppDownloadPlatform.IOS
    return AppDownloadPlatform.OTHER


def resolve_app_download_platform(user_agent, platform_override):
    if platform_override in FORCED_APP_DOWNLOAD_PLATFORMS:
        return platform_override
    return detect_app_download_platform(user_agent)


def resolve_app_download_entry(platform_override, platform):
    """Classify hit without changing QR URL (`/scan` → `/app/`)."""
    if platform_override in FORCED_APP_DOWNLOAD_PLATFORMS:
        return AppDownloadEntry.PLATFORM_QUERY
    if platform == AppDownloadPlatform.OTHER:
        return AppDownloadEntry.CHOOSER
    return AppDownloadEntry.UA


def is_app_download_bot_user_agent(user_agent):
    if not user_agent:
        return False
    return bool(APP_DOWNLOAD_BOT_USER_AGENT_REGEX.search(user_agent))


def truncate_user_agent(user_agent):
    if not user_agent:
        return ""
    return user_agent[:APP_DOWNLOAD_USER_AGENT_MAX_LENGTH]


def build_app_download_track_url(*, platform, source, campaign):
    query = {"platform": platform}
    if source:
        query["src"] = source
    if campaign:
        query["campaign"] = campaign
    return f"/app/?{urlencode(query)}"


def record_app_download_click(
    *,
    platform,
    entry,
    destination_url,
    user_agent,
    ip_address,
    source,
    campaign,
    referer,
):
    try:
        return AppDownloadClick.objects.create(
            platform=platform,
            entry=entry,
            destination_url=destination_url,
            user_agent=truncate_user_agent(user_agent),
            ip_address=ip_address or None,
            source=source,
            campaign=campaign,
            referer=referer,
        )
    except DatabaseError:
        logger.exception("Failed to record app download click")
        return None


class AppDownloadRedirectView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AppDownloadThrottle]

    def get(self, request, *args, **kwargs):
        user_agent = get_request_user_agent(request) or ""
        platform_override = (request.query_params.get("platform") or "").strip().lower()
        platform = resolve_app_download_platform(user_agent, platform_override)
        entry = resolve_app_download_entry(platform_override, platform)
        destination_url = APP_DOWNLOAD_DESTINATION_BY_PLATFORM.get(platform, "")
        source = (request.query_params.get("src") or "")[:128]
        campaign = (request.query_params.get("campaign") or "")[:128]
        referer = (request.META.get("HTTP_REFERER") or "")[:512]

        if not is_app_download_bot_user_agent(user_agent):
            record_app_download_click(
                platform=platform,
                entry=entry,
                destination_url=destination_url,
                user_agent=user_agent,
                ip_address=get_request_ip_address(request),
                source=source,
                campaign=campaign,
                referer=referer,
            )

        if destination_url:
            return HttpResponseRedirect(destination_url)

        return render(
            request._request,
            APP_DOWNLOAD_CHOOSER_TEMPLATE,
            {
                "ios_track_url": build_app_download_track_url(
                    platform=AppDownloadPlatform.IOS,
                    source=source,
                    campaign=campaign,
                ),
                "android_track_url": build_app_download_track_url(
                    platform=AppDownloadPlatform.ANDROID,
                    source=source,
                    campaign=campaign,
                ),
            },
        )
