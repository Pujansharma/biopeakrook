"""Standard {success, data} response envelope for pre-consultation APIs."""

from rest_framework.response import Response


def _data_without_success_key(data: dict) -> dict:
    return {key: value for key, value in data.items() if key != "success"}


def pre_consultation_response(
    *, success: bool, status_code: int, data: dict | None = None
) -> Response:
    body = {"success": success}
    if data is not None:
        body["data"] = _data_without_success_key(data)
    return Response(body, status=status_code)


def pre_consultation_paginated_response(
    *,
    success: bool,
    status_code: int,
    count: int,
    next_link: str | None,
    previous_link: str | None,
    results: list,
) -> Response:
    body = {
        "success": success,
        "count": count,
        "next": next_link,
        "previous": previous_link,
        "data": results,
    }
    return Response(body, status=status_code)
