"""Shared GET/PUT orchestration for all pre-consultation layer endpoints.

Resolves optional customer profile, validates input, and persists layer data.
Downstream rows are updated surgically in each layer persist handler (no blanket cascade).
"""

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from accounts.customers.models import CustomerProfile
from accounts.users.models import User
from core.utils.request import Request
from pre_consultation.customer_profile import resolve_customer_profile_for_request
from pre_consultation.layers.base import LayerHandler
from pre_consultation.layers.serialization import serialize_layer_payload
from pre_consultation.models import PreConsultationSession
from pre_consultation.serializers import PreConsultationSessionResponseSerializer
from pre_consultation.session_utils import (
    get_user_pre_consultation_session,
    guard_onboarding_incomplete_for_mutation,
    is_session_completed,
)
from pre_consultation.utils.api import pre_consultation_response


def resolve_request_customer_profile(request: Request) -> CustomerProfile | None:
    return resolve_customer_profile_for_request(
        request.user,
        getattr(request, "customer_profile_id", None),
    )


def resolve_customer_profile_for_handler(
    request: Request,
    layer_handler: LayerHandler,
) -> CustomerProfile | None:
    if not layer_handler.needs_customer_profile:
        return None
    return resolve_request_customer_profile(request)


def call_layer_load_payload(
    layer_handler: LayerHandler,
    user: User,
    session: PreConsultationSession,
    customer_profile: CustomerProfile | None = None,
) -> dict | None:
    if customer_profile is None:
        return layer_handler.load_payload(user, session)
    return layer_handler.load_payload(user, session, customer_profile=customer_profile)


def call_layer_persist_payload(
    layer_handler: LayerHandler,
    user: User,
    session: PreConsultationSession,
    validated_data: dict,
    customer_profile: CustomerProfile | None = None,
) -> None:
    if customer_profile is None:
        layer_handler.persist_payload(user, session, validated_data)
        return
    layer_handler.persist_payload(
        user,
        session,
        validated_data,
        customer_profile=customer_profile,
    )


def build_put_serializer_context(
    layer_handler: LayerHandler,
    session: PreConsultationSession,
    request: Request,
) -> dict:
    if layer_handler.build_put_serializer_context is None:
        return {}
    return layer_handler.build_put_serializer_context(session, request)


def execute_layer_get(request: Request, layer_handler: LayerHandler) -> Response:
    session = get_user_pre_consultation_session(request.user)

    if not layer_handler.is_implemented:
        return pre_consultation_response(
            success=True,
            data={"layer_id": layer_handler.layer_id, "payload": None},
            status_code=status.HTTP_200_OK,
        )

    customer_profile = resolve_customer_profile_for_handler(request, layer_handler)
    payload = call_layer_load_payload(
        layer_handler,
        request.user,
        session,
        customer_profile=customer_profile,
    )
    response_data = serialize_layer_payload(
        layer_handler.response_serializer_class,
        payload,
    )
    return pre_consultation_response(
        success=True,
        data=response_data,
        status_code=status.HTTP_200_OK,
    )


def execute_layer_put(request: Request, layer_handler: LayerHandler) -> Response:
    session = get_user_pre_consultation_session(request.user)

    if is_session_completed(session):
        return pre_consultation_response(
            success=False,
            data=PreConsultationSessionResponseSerializer(session).data,
            status_code=status.HTTP_409_CONFLICT,
        )

    onboarding_conflict = guard_onboarding_incomplete_for_mutation(request, session)
    if onboarding_conflict is not None:
        return onboarding_conflict

    if not layer_handler.is_implemented:
        return pre_consultation_response(
            success=False,
            data={
                "layer_id": layer_handler.layer_id,
                "message": "Layer not implemented.",
            },
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
        )

    serializer_context = build_put_serializer_context(layer_handler, session, request)
    request_serializer = layer_handler.request_serializer_class(
        data=request.data,
        context=serializer_context,
    )
    request_serializer.is_valid(raise_exception=True)

    customer_profile = resolve_customer_profile_for_handler(request, layer_handler)
    validated_data = request_serializer.validated_data
    with transaction.atomic():
        call_layer_persist_payload(
            layer_handler,
            request.user,
            session,
            validated_data,
            customer_profile=customer_profile,
        )

    if not layer_handler.put_includes_data:
        return pre_consultation_response(
            success=True,
            status_code=status.HTTP_200_OK,
        )

    if (
        layer_handler.load_put_payload is not None
        and layer_handler.put_response_serializer_class is not None
    ):
        payload = layer_handler.load_put_payload(request.user, session)
        response_serializer_class = layer_handler.put_response_serializer_class
    else:
        payload = call_layer_load_payload(
            layer_handler,
            request.user,
            session,
            customer_profile=customer_profile,
        )
        response_serializer_class = layer_handler.response_serializer_class

    response_data = serialize_layer_payload(
        response_serializer_class,
        payload,
    )
    return pre_consultation_response(
        success=True,
        data=response_data,
        status_code=status.HTTP_200_OK,
    )
