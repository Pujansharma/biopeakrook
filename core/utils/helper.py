import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile
from django.utils.http import parse_header_parameters
from rest_framework.request import Request


def response_format(detail, data=None):
    context = {"detail": detail}
    if data is not None:
        if all(key in data for key in ["count", "next", "previous", "results"]):
            results = data.pop("results")
            return {**context, **data, "data": results}
        return {**context, "data": data}
    return context


def normalize_ip_address(value):
    if not value:
        return None
    candidate = value.strip().strip("[]")
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def get_request_ip_address(request: Request):
    """Client IP behind a trusted proxy (ALB appends the real hop last)."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return normalize_ip_address(forwarded_for.split(",")[-1])
    return normalize_ip_address(request.META.get("REMOTE_ADDR"))


def get_request_user_agent(request: Request):
    return request.META.get("HTTP_USER_AGENT")


def extract_filename(response: requests.Response, url: str) -> str:
    content_disposition = response.headers.get("Content-Disposition", "")
    _, params = parse_header_parameters(content_disposition)
    filename = params.get("filename")
    if filename:
        return filename
    path_filename = Path(urlparse(url).path).name
    return path_filename or "Unknown"


def fetch_file_from_url(url: str | None) -> ContentFile | None:
    if not url:
        return None
    response = requests.get(url, stream=True)
    if not response.ok:
        return None
    content = response.content
    file = ContentFile(content, name=extract_filename(response, url))
    return file
