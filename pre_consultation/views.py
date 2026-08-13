"""Session lifecycle endpoints: start, complete, and final result summary."""

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from accounts.customers.utils.db import mark_customer_profile_onboarding_completed_for_user
from core.utils.view_types import GetMethodMixin, PostMethodMixin
from core.utils.views import BaseGenericAPIView
from pre_consultation.models import (
    PreConsultationSession,
    PreConsultationSessionArtifacts,
)
from pre_consultation.result import (
    PreConsultationSessionResultSerializer,
    PreConsultationSessionResultV2Serializer,
    build_session_result_payload,
    build_session_result_v2_payload,
)
from pre_consultation.serializers import (
    PreConsultationSessionResponseSerializer,
    PreConsultationSessionStartSerializer,
)
from pre_consultation.session_utils import (
    get_user_pre_consultation_session,
    guard_lead_onboarding_completed_for_start,
    is_session_completed,
)
from pre_consultation.utils.api import pre_consultation_response
from pre_consultation.utils.constants import (
    PreConsultationLayerProgression,
    PreConsultationSessionStatus,
    PreConsultationArtifactGenerationStatus,
)
from pre_consultation.utils.directive import get_directive_schema_id
from pre_consultation.utils.schema import (
    PRE_CONSULTATION_SESSION_TAG,
    PreConsultationSessionConflictEnvelope,
    pre_consultation_data_envelope,
)
from pre_consultation.generation_webhook import trigger_post_completion_generation


SESSION_CONFLICT_ENVELOPE = PreConsultationSessionConflictEnvelope
SESSION_DATA_ENVELOPE = pre_consultation_data_envelope(
    PreConsultationSessionResponseSerializer
)
SESSION_RESULT_ENVELOPE = pre_consultation_data_envelope(
    PreConsultationSessionResultSerializer
)
SESSION_RESULT_V2_ENVELOPE = pre_consultation_data_envelope(
    PreConsultationSessionResultV2Serializer
)


@extend_schema_view(
    post=extend_schema(
        tags=[PRE_CONSULTATION_SESSION_TAG],
        description="Step 1 — Start or resume pre-consultation session (one per user).",
        request=PreConsultationSessionStartSerializer,
        responses={
            200: SESSION_DATA_ENVELOPE,
            201: SESSION_DATA_ENVELOPE,
            409: SESSION_CONFLICT_ENVELOPE,
        },
    ),
)
class PreConsultationSessionStartView(BaseGenericAPIView, PostMethodMixin):
    permission_classes = [IsAuthenticated]
    serializer_class = PreConsultationSessionStartSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        onboarding_conflict = guard_lead_onboarding_completed_for_start(request)
        if onboarding_conflict is not None:
            return onboarding_conflict

        session = PreConsultationSession.objects.filter(user=request.user).first()

        if session:
            if session.status == PreConsultationSessionStatus.COMPLETED:
                response_data = PreConsultationSessionResponseSerializer(session).data
                return pre_consultation_response(
                    success=False,
                    data=response_data,
                    status_code=status.HTTP_409_CONFLICT,
                )

            for field_name, field_value in serializer.validated_data.items():
                setattr(session, field_name, field_value)
            session.save(
                update_fields=[*serializer.validated_data.keys(), "updated_at"]
            )
            response_data = PreConsultationSessionResponseSerializer(session).data
            return pre_consultation_response(
                success=True,
                data=response_data,
                status_code=status.HTTP_200_OK,
            )

        session = PreConsultationSession.objects.create(
            user=request.user,
            directive_schema_id=get_directive_schema_id(),
            status=PreConsultationSessionStatus.IN_PROGRESS,
            current_layer=PreConsultationLayerProgression.PATIENT_BASELINE,
            **serializer.validated_data,
        )
        response_data = PreConsultationSessionResponseSerializer(session).data
        return pre_consultation_response(
            success=True,
            data=response_data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_SESSION_TAG],
        description="Step 11 — Health map summary via GET result (in-progress or completed).",
        responses={
            200: SESSION_RESULT_ENVELOPE,
            404: None,
        },
    ),
)
class PreConsultationSessionResultView(BaseGenericAPIView, GetMethodMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        session = get_user_pre_consultation_session(request.user)

        result_payload = build_session_result_payload(session)
        response_data = PreConsultationSessionResultSerializer(result_payload).data
        return pre_consultation_response(
            success=True,
            data=response_data,
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_SESSION_TAG],
        description=(
            "Step 11 v2 — Health map summary plus previous_layer "
            "(same routing as patient_goals_priorities)."
        ),
        responses={
            200: SESSION_RESULT_V2_ENVELOPE,
            404: None,
        },
    ),
)
class PreConsultationSessionResultV2View(BaseGenericAPIView, GetMethodMixin):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        session = get_user_pre_consultation_session(request.user)

        result_payload = build_session_result_v2_payload(session)
        response_data = PreConsultationSessionResultV2Serializer(result_payload).data
        return pre_consultation_response(
            success=True,
            data=response_data,
            status_code=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        tags=[PRE_CONSULTATION_SESSION_TAG],
        description=(
            "Step 12 — Mark session completed. "
            "Requires current_layer = patient_health_map."
        ),
        request=None,
        responses={
            200: SESSION_DATA_ENVELOPE,
            409: SESSION_CONFLICT_ENVELOPE,
        },
    ),
)
class PreConsultationSessionCompleteView(BaseGenericAPIView, PostMethodMixin):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        session = get_user_pre_consultation_session(request.user)

        if is_session_completed(session):
            return pre_consultation_response(
                success=False,
                data=PreConsultationSessionResponseSerializer(session).data,
                status_code=status.HTTP_409_CONFLICT,
            )

        if session.current_layer != PreConsultationLayerProgression.PATIENT_HEALTH_MAP:
            raise ValidationError(
                "Session must be at patient_health_map before completion."
            )

        with transaction.atomic():
            session.status = PreConsultationSessionStatus.COMPLETED
            session.completed_at = timezone.now()
            session.save(update_fields=["status", "completed_at", "updated_at"])

            mark_customer_profile_onboarding_completed_for_user(
                request.user,
                getattr(request, "customer_profile_id", None),
            )

            PreConsultationSessionArtifacts.objects.update_or_create(
                session=session,
                defaults={"generation_status": PreConsultationArtifactGenerationStatus.PENDING},
            )

            transaction.on_commit(
                lambda: trigger_post_completion_generation(session.pk, session.user_id)
            )

        return pre_consultation_response(
            success=True,
            data=PreConsultationSessionResponseSerializer(session).data,
            status_code=status.HTTP_200_OK,
        )
