"""Session lifecycle endpoints: start, complete, and final result summary."""

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from accounts.customers.models import Customer
from core.utils.view_types import GetMethodMixin, PostMethodMixin
from core.utils.views import BaseGenericAPIView
from pre_consultation.models import (
    PreConsultationSession,
    PreConsultationSessionArtifacts,
)
from pre_consultation.result import (
    PreConsultationSessionResultSerializer,
    build_session_result_payload,
)
from pre_consultation.result_session import get_result_session_context
from pre_consultation.serializers import (
    PreConsultationSessionResponseSerializer,
    PreConsultationSessionStartSerializer,
)
from pre_consultation.customer_profile import resolve_customer_profile_for_request
from pre_consultation.session_utils import (
    get_user_pre_consultation_session,
    guard_lead_onboarding_complete_for_start,
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
from leads.utils.db import mark_lead_onboarding_completed_for_user

SESSION_CONFLICT_ENVELOPE = PreConsultationSessionConflictEnvelope
SESSION_DATA_ENVELOPE = pre_consultation_data_envelope(
    PreConsultationSessionResponseSerializer
)
SESSION_RESULT_ENVELOPE = pre_consultation_data_envelope(
    PreConsultationSessionResultSerializer
)
from intelligence_engine.preconsultation.summarize import asummarize_patient
from intelligence_engine.preconsultation.extract_insights import aextract_insights_batch


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

        onboarding_conflict = guard_lead_onboarding_complete_for_start(request)
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

            if Customer.objects.filter(user=request.user).exists():
                customer_profile = resolve_customer_profile_for_request(
                    request.user,
                    getattr(request, "customer_profile_id", None),
                )
                customer_profile.is_onboarding_complete = True
                customer_profile.save(
                    update_fields=["is_onboarding_complete", "updated_at"]
                )

            mark_lead_onboarding_completed_for_user(request.user)

            PreConsultationSessionArtifacts.objects.update_or_create(
                session=session,
                defaults={"generation_status": PreConsultationArtifactGenerationStatus.PENDING},
            )
            transaction.on_commit(
                lambda: spawn_summarization(session.pk, session.user_id)
            )

            transaction.on_commit(
                lambda: spawn_report_insights_extraction(session.pk, session.user_id)
            )


        '''
        INCLUDES:
            PRECONSULTATION SUMMARY
            FAMILY RISK SUMMARY
            QUICK SUMMARY
            DOCTOR'S CHECKLIST

        FUNCTION CALL:
            asummarize_patient(
                client_details = {
                    "patient_baseline": {
                        "id": "",
                        "first_name": "",
                        "last_name": "",
                        "contact_email": "",
                        "date_of_birth": "",
                        "gender": ""
                    },
                    "category_selections": [
                        {
                        "category_label": ""
                        }
                    ],
                    "concerns": [
                        {
                        "concern_label": "",
                        "functional_impact_id": "",
                        "functional_impact_label": "",
                        "duration_impact_label": "",
                        "progression_impact_id": "",
                        "progression_impact_label": "",
                        "confidence_score": 0,
                        "probe_flagged": false,
                        "probe_question_count": 0,
                        "symptoms": [
                            {
                            "symptom_label": ""
                            }
                        ],
                        "concern_sources": [
                            {
                            "source_label": ""
                            }
                        ],
                        "family_history": [
                            {
                            "relation_label": "",
                            "age_band_label": ""
                            }
                        ],
                        "cluster_probe_answers": [
                            {
                            "probe_label": "",
                            "value": ""
                            }
                        ]
                        }
                    ],
                    "medical_history": {
                        "diagnoses": [
                        {
                            "diagnosis_label": ""
                        }
                        ],
                        "medications": [
                        {
                            "name": "",
                            "dosage": "",
                            "frequency": "",
                            "duration": ""
                        }
                        ],
                        "allergies": [
                        {
                            "name": ""
                        }
                        ],
                        "surgeries": [
                        {
                            "name": "",
                            "area": "",
                            "performed_when": "",
                            "reason": ""
                        }
                        ],
                        "sexual_health_answers": [
                        {
                            "question_label": "",
                            "option_id": "",
                            "option_label": ""
                        }
                        ]
                    },
                    "cluster_scores": [
                        {
                        "cluster_label": "",
                        "final_score": 0,
                        "bucket_id": "",
                        "bucket_label": "",
                        "lifestyle_signals_triggered": [
                            {
                            "signal_label": ""
                            }
                        ],
                        "family_risk_contribution": 0,
                        "validation_skip_reason": ""
                        }
                    ],
                    "health_goals": [
                        {
                        "goal_label": "",
                        "priority": 0
                        }
                    ],
                    "lifestyle_answers": [
                        {
                        "field_label": "",
                        "option_value": "",
                        "option_label": ""
                        }
                    ]
                },
                trigger_webhook = True
            ) 
            -> 
            {
                "output_style": "" (same as input, not required),
                "output_size": "" (same as input, not required),
                "preconsultation_summary": "",
                "quick_summary": "",
                "family_risk_summary": "",
                "preconsultation_checklist": [
                    {
                    "probe": "", (main content)
                    "tag": "",
                    "score": int,
                    "reason": "" (supplementary, could be concatenated)
                    }
                ]
            }
        '''


        '''
        INCLUDES:
            MEDICAL REPORT INSIGHTS GENERATION

        FUNCTION CALL:
            aextract_insights_batch(
                "reports": [
                    {
                        "filebytestream": ,
                        "filename": ",
                        "metadata": {
                            "doc_id": "",
                            "upload_date": YYYY-MM-DD (optional)
                        },
                    "client_details": {
                            "client_id": "",
                            "name": "",
                            "age": "",
                            "gender": ""
                        }
                    }
                ]
            )
            ->
            {
            "results": [
                {
                "doc_id": "",
                "title": "",
                "name": null,
                "upload_date": null,
                "owner": null,
                "summary": "",
                "contains_biomarkers": boolean,
                "abnormal_biomarkers": 
                    [
                        {
                            "name": "",
                            "value": "", // Could be phrase-values such as High, Low, A-grade etc.
                            "unit": "",
                            "reference_range": ""
                        }
                    ]
                }
            ],
            "skipped": [
                {
                "doc_id": null,
                "filename": null,
                "reason": "",
                "detail": ""
                }
            ]
            }
        '''


        return pre_consultation_response(
            success=True,
            data=PreConsultationSessionResponseSerializer(session).data,
            status_code=status.HTTP_200_OK,
        )
