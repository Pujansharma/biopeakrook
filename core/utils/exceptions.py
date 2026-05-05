from django.http import JsonResponse, Http404
from django.utils.text import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    ParseError,
    PermissionDenied,
)
from rest_framework.generics import get_object_or_404 as base_get_object_or_404
from rest_framework.views import exception_handler

from core.utils.helper import response_format


def not_found(request, exception, *args, **kwargs):
    """
    Generic 404 error handler.
    """
    data = response_format("Not Found (404)")
    return JsonResponse(data, status=404)


def server_error(request):
    """
    Generic 500 error handler.
    """
    data = response_format("Server Error (500)")
    return JsonResponse(data, status=500)


def parse_response_detail(response):
    if isinstance(response.data, list):
        return response.data[0]
    detail = response.data.pop("detail", response.data)
    if isinstance(detail, list) and len(detail) == 1:
        return detail[0]
    return detail


def base_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response:
        detail = parse_response_detail(response)
        response.data = response_format(detail=detail)
    return response


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("Unknown error occurred.")
    default_code = "service_unavailable"


class ServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _("Server error occurred.")
    default_code = "internal_server_error"


class NoDataFound(APIException):
    status_code = status.HTTP_204_NO_CONTENT
    default_detail = _("No content found.")
    default_code = "no_content"


def get_object_or_no_data(queryset, detail=None, *args, **kwargs):
    try:
        return base_get_object_or_404(queryset, *args, **kwargs)
    except Http404:
        raise NoDataFound(detail)


def get_object_or_404(queryset, detail=None, *args, **kwargs):
    try:
        return base_get_object_or_404(queryset, *args, **kwargs)
    except Http404:
        raise NotFound(detail)


def get_not_found(get_object_method, detail=None):
    try:
        return get_object_method()
    except Http404:
        raise NotFound(detail)


def bad_request(detail=None):
    raise ParseError(detail)


def permission_denied(detail=None):
    raise PermissionDenied(detail)
