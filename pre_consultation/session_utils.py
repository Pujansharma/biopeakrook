"""Session lookup helpers shared by views and layer execution."""

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from core.utils.request import Request
from accounts.customers.utils.db import (
    is_customer_profile_ready_for_onboarding_session_for_user,
)
from leads.utils.db import (
    is_lead_ready_for_onboarding_session_for_user,
    user_has_lead_for_phone,
)
from pre_consultation.customer_profile import resolve_customer_profile_for_request
from pre_consultation.models import PreConsultationSession
from pre_consultation.serializers import PreConsultationSessionResponseSerializer
from pre_consultation.utils.api import pre_consultation_response
from pre_consultation.utils.constants import PreConsultationSessionStatus


def get_user_pre_consultation_session(user) -> PreConsultationSession:
    session = PreConsultationSession.objects.filter(user=user).first()
    if session is None:
        raise NotFound("Pre-consultation session not found.")
    return session


def is_session_completed(session: PreConsultationSession) -> bool:
    return session.status == PreConsultationSessionStatus.COMPLETED


def is_customer_onboarding_completed(request: Request) -> bool:
    customer_profile = resolve_customer_profile_for_request(
        request.user,
        getattr(request, "customer_profile_id", None),
    )
    return customer_profile.is_onboarding_completed


def build_onboarding_completed_conflict_response(
    user,
    session: PreConsultationSession | None = None,
) -> Response:
    if session is None:
        session = PreConsultationSession.objects.filter(user=user).first()
    response_data = (
        PreConsultationSessionResponseSerializer(session).data
        if session is not None
        else {}
    )
    return pre_consultation_response(
        success=False,
        data=response_data,
        status_code=status.HTTP_409_CONFLICT,
    )


def guard_onboarding_incomplete_for_mutation(
    request: Request,
    session: PreConsultationSession | None = None,
) -> Response | None:
    if not is_customer_onboarding_completed(request):
        return None
    return build_onboarding_completed_conflict_response(request.user, session)


def is_user_ready_for_onboarding_session_start(request: Request) -> bool:
    customer_profile_id = getattr(request, "customer_profile_id", None)
    if user_has_lead_for_phone(request.user):
        return is_lead_ready_for_onboarding_session_for_user(request.user)
    return is_customer_profile_ready_for_onboarding_session_for_user(
        request.user,
        customer_profile_id,
    )


def guard_lead_onboarding_completed_for_start(
    request: Request,
    session: PreConsultationSession | None = None,
) -> Response | None:
    if is_user_ready_for_onboarding_session_start(request):
        return None
    return build_onboarding_completed_conflict_response(request.user, session)
