"""Medical history layer view — GET/PUT plus multipart medical-report upload."""

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils.request import Request
from core.utils.view_types import GetMethodMixin, PostMethodMixin, PutMethodMixin
from core.utils.views import BaseGenericAPIView
from pre_consultation.layer_execution import execute_layer_get, execute_layer_put
from pre_consultation.layers.patient_medical_history_context import (
    PatientMedicalHistoryContextMedicalReportResponseSerializer,
    PatientMedicalHistoryContextMedicalReportUploadSerializer,
    PatientMedicalHistoryContextRequestSerializer,
    PatientMedicalHistoryContextResponseSerializer,
    persist_medical_history_medical_report_upload,
)
from pre_consultation.layers.registry import LAYER_HANDLERS
from pre_consultation.layers.serialization import serialize_layer_payload
from pre_consultation.serializers import PreConsultationSessionResponseSerializer
from pre_consultation.session_utils import (
    get_user_pre_consultation_session,
    is_session_completed,
)
from pre_consultation.utils.api import pre_consultation_response
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.schema import (
    CUSTOMER_PROFILE_HEADER,
    PRE_CONSULTATION_LAYER_TAG,
    PreConsultationEmptySuccessSerializer,
    PreConsultationLayerNotImplementedSerializer,
    PreConsultationSessionConflictEnvelope,
    build_layer_get_description,
    build_layer_put_description,
    pre_consultation_data_envelope,
)
from pre_consultation.utils.throttling import (
    PreConsultationGetThrottle,
    PreConsultationPostThrottle,
    PreConsultationPutThrottle,
)

_MEDICAL_HISTORY_HANDLER = LAYER_HANDLERS[
    PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT
]
_GET_RESPONSE = pre_consultation_data_envelope(
    PatientMedicalHistoryContextResponseSerializer,
)
_POST_RESPONSE = pre_consultation_data_envelope(
    PatientMedicalHistoryContextMedicalReportResponseSerializer,
)
_PUT_RESPONSES = {
    200: PreConsultationEmptySuccessSerializer,
    409: PreConsultationSessionConflictEnvelope,
    501: PreConsultationLayerNotImplementedSerializer,
}


def execute_medical_history_report_upload(request: Request) -> Response:
    session = get_user_pre_consultation_session(request.user)

    if is_session_completed(session):
        return pre_consultation_response(
            success=False,
            data=PreConsultationSessionResponseSerializer(session).data,
            status_code=status.HTTP_409_CONFLICT,
        )

    upload_serializer = PatientMedicalHistoryContextMedicalReportUploadSerializer(
        data=request.data,
    )
    upload_serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        report_payload = persist_medical_history_medical_report_upload(
            session,
            upload_serializer.validated_data["file"],
        )

    response_data = serialize_layer_payload(
        PatientMedicalHistoryContextMedicalReportResponseSerializer,
        report_payload,
    )
    return pre_consultation_response(
        success=True,
        data=response_data,
        status_code=status.HTTP_200_OK,
    )


@extend_schema_view(
    get=extend_schema(
        tags=[PRE_CONSULTATION_LAYER_TAG],
        parameters=[CUSTOMER_PROFILE_HEADER],
        description=build_layer_get_description(
            PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT,
        ),
        responses={200: _GET_RESPONSE},
    ),
    post=extend_schema(
        tags=[PRE_CONSULTATION_LAYER_TAG],
        description=(
            "Upload one medical report file for the active session. "
            "Returns 409 when the session is completed."
        ),
        request=PatientMedicalHistoryContextMedicalReportUploadSerializer,
        responses={200: _POST_RESPONSE, 409: PreConsultationSessionConflictEnvelope},
    ),
    put=extend_schema(
        tags=[PRE_CONSULTATION_LAYER_TAG],
        parameters=[CUSTOMER_PROFILE_HEADER],
        description=build_layer_put_description(
            PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT,
        ),
        request=PatientMedicalHistoryContextRequestSerializer,
        responses=_PUT_RESPONSES,
    ),
)
class PatientMedicalHistoryContextLayerView(
    BaseGenericAPIView,
    GetMethodMixin,
    PostMethodMixin,
    PutMethodMixin,
):
    permission_classes = [IsAuthenticated]
    throttle_classes = [
        PreConsultationGetThrottle,
        PreConsultationPostThrottle,
        PreConsultationPutThrottle,
    ]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, *args, **kwargs):
        return execute_layer_get(request, _MEDICAL_HISTORY_HANDLER)

    def post(self, request, *args, **kwargs):
        return execute_medical_history_report_upload(request)

    def put(self, request, *args, **kwargs):
        return execute_layer_put(request, _MEDICAL_HISTORY_HANDLER)
