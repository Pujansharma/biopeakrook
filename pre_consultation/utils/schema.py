"""OpenAPI schema helpers and layer endpoint descriptions for drf-spectacular."""

from typing import Type

from drf_spectacular.utils import OpenApiParameter, inline_serializer
from rest_framework import serializers

from pre_consultation.serializers import PreConsultationSessionResponseSerializer
from pre_consultation.utils.constants import PreConsultationLayerProgression

CUSTOMER_PROFILE_HEADER = OpenApiParameter(
    name="X-Customer-Profile-ID",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Target family profile UUID. Defaults to the customer's main profile.",
)

RESULT_LIST_CENTER_HEADER = OpenApiParameter(
    name="X-Center-ID",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "When provided, restricts results to converted customers assigned to this center."
    ),
)

RESULT_LIST_SEARCH_PARAM = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Filter by customer full name, phone, or contact email "
        "(prefix match on name/phone; prefix and contains on email)."
    ),
)

RESULT_LIST_PAGE_PARAM = OpenApiParameter(
    name="page",
    type=int,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Page number (default 1).",
)

RESULT_LIST_LIMIT_PARAM = OpenApiParameter(
    name="limit",
    type=int,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Page size (default 10, max 50).",
)

PRE_CONSULTATION_LAYER_TAG = "Pre-Consultation Layers"
PRE_CONSULTATION_SESSION_TAG = "Pre-Consultation Session"
PRE_CONSULTATION_RESULT_TAG = "Pre-Consultation Result"

PRE_CONSULTATION_OPENAPI_TITLE = "Biopeak Nexus Pre-Consultation API"
PRE_CONSULTATION_OPENAPI_DESCRIPTION = (
    "Customer pre-consultation wizard API. "
    "Call endpoints in flow order: "
    "start → patient_baseline → patient_category → patient_concern → "
    "patient_symptom → patient_concern_probe → patient_medical_history_context → "
    "patient_lifestyle_environment → patient_cluster_probe (conditional) → "
    "patient_goals_priorities → patient_health_map (GET result) → complete. "
    "Human-readable reference: api-pre-consultation-v1.md / api-pre-consultation-v2.md. "
    "OpenAPI schema: /pre-consultation/openapi/ · Swagger UI: /pre-consultation/openapi/docs/."
)

PRE_CONSULTATION_PATH_ORDER: tuple[str, ...] = (
    "/pre-consultation/session/start/",
    "/pre-consultation/session/patient_baseline/",
    "/pre-consultation/session/patient_baseline/v2/",
    "/pre-consultation/session/patient_category/",
    "/pre-consultation/session/patient_concern/",
    "/pre-consultation/session/patient_concern/v2/",
    "/pre-consultation/session/patient_symptom/",
    "/pre-consultation/session/patient_concern_probe/",
    "/pre-consultation/session/patient_concern_probe/v2/",
    "/pre-consultation/session/patient_medical_history_context/",
    "/pre-consultation/session/patient_lifestyle_environment/",
    "/pre-consultation/session/patient_lifestyle_environment/v2/",
    "/pre-consultation/session/patient_cluster_probe/",
    "/pre-consultation/session/patient_cluster_probe/v2/",
    "/pre-consultation/session/patient_goals_priorities/",
    "/pre-consultation/session/patient_goals_priorities/v2/",
    "/pre-consultation/session/result/",
    "/pre-consultation/session/result/v2/",
    "/pre-consultation/session/complete/",
    "/pre-consultation/result/list/",
    "/pre-consultation/result/{user_id}/overview/",
    "/pre-consultation/result/{user_id}/checklist/{item_id}/",
    "/pre-consultation/result/{user_id}/context/",
    "/pre-consultation/result/{user_id}/family-risk/",
    "/pre-consultation/result/{user_id}/health-map/",
    "/pre-consultation/result/{user_id}/clusters/",
    "/pre-consultation/result/{user_id}/lifestyle/",
    "/pre-consultation/result/{user_id}/medical-context/",
    "/pre-consultation/result/{user_id}/surgery/",
    "/pre-consultation/result/{user_id}/medical-reports/",
    "/pre-consultation/result/{user_id}/raw-data/",
    "/pre-consultation/result/{user_id}/notes/",
)

LAYER_STEP_SUMMARIES: dict[str, str] = {
    PreConsultationLayerProgression.PATIENT_BASELINE: "Demographics and address",
    PreConsultationLayerProgression.PATIENT_CATEGORY: "Health category selection",
    PreConsultationLayerProgression.PATIENT_CONCERN: "Concern selection",
    PreConsultationLayerProgression.PATIENT_SYMPTOM: "Symptoms, sources, family history",
    PreConsultationLayerProgression.PATIENT_CONCERN_PROBE: "Impact probes per concern",
    PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT: (
        "Diagnoses, medications, surgeries, sexual health, medical reports"
    ),
    PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT: (
        "Lifestyle questionnaire and cluster scoring"
    ),
    PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE: (
        "Cluster validation probes (conditional, cluster final score 65–80)"
    ),
    PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES: "Ranked health goals",
}

LAYER_EXECUTION_STEPS: dict[str, int] = {
    PreConsultationLayerProgression.PATIENT_BASELINE: 2,
    PreConsultationLayerProgression.PATIENT_CATEGORY: 3,
    PreConsultationLayerProgression.PATIENT_CONCERN: 4,
    PreConsultationLayerProgression.PATIENT_SYMPTOM: 5,
    PreConsultationLayerProgression.PATIENT_CONCERN_PROBE: 6,
    PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT: 7,
    PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT: 8,
    PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE: 9,
    PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES: 10,
}

PRE_CONSULTATION_SPECTACULAR_SETTINGS: dict = {
    "TITLE": PRE_CONSULTATION_OPENAPI_TITLE,
    "DESCRIPTION": PRE_CONSULTATION_OPENAPI_DESCRIPTION,
    "COMPONENT_SPLIT_REQUEST": True,
    "PREPROCESSING_HOOKS": [
        "pre_consultation.utils.schema.filter_pre_consultation_endpoints",
    ],
    "POSTPROCESSING_HOOKS": [
        "pre_consultation.utils.schema.postprocess_pre_consultation_schema",
    ],
}


PreConsultationEmptySuccessSerializer = inline_serializer(
    name="PreConsultationEmptySuccess",
    fields={
        "success": serializers.BooleanField(),
    },
)


PreConsultationLayerNotImplementedSerializer = inline_serializer(
    name="PreConsultationLayerNotImplemented",
    fields={
        "success": serializers.BooleanField(),
        "data": inline_serializer(
            name="PreConsultationLayerNotImplementedData",
            fields={
                "layer_id": serializers.CharField(),
                "message": serializers.CharField(),
            },
        ),
    },
)


class PatientLifestyleEnvironmentPutRequestSerializer(serializers.Serializer):
    """OpenAPI-only flat lifestyle PUT body (all directive fields required)."""

    sleep_duration = serializers.CharField(
        help_text="e.g. <5 hrs, 5-6 hrs, 6-7 hrs, 7-8 hrs, 8+ hrs"
    )
    eating_pattern = serializers.CharField(
        help_text="e.g. home_cooked_veg, mixed, eating_out, high_sweets, irregular_meals, restrictive_diet"
    )
    sugary_drinks = serializers.CharField(help_text="e.g. rarely, sometimes, daily")
    activity_level = serializers.CharField(
        help_text="e.g. sedentary, light, moderate, active, very_active"
    )
    desk_job = serializers.CharField(help_text="yes or no")
    stress_level = serializers.CharField(
        help_text="e.g. low, mild, moderate, high, very_high"
    )
    hydration = serializers.CharField(help_text="e.g. lt_1L, 1-2L, 2-3L, 3L_plus")
    alcohol = serializers.CharField(help_text="e.g. none, occasional, frequent")
    tobacco = serializers.CharField(
        help_text="e.g. none, smoked, smokeless, both, former"
    )


_ENVELOPE_CACHE: dict[str, Type[serializers.Serializer]] = {}


def pre_consultation_data_envelope(
    inner_serializer_class: Type[serializers.Serializer],
) -> Type[serializers.Serializer]:
    cache_key = f"data:{inner_serializer_class.__name__}"
    if cache_key not in _ENVELOPE_CACHE:
        _ENVELOPE_CACHE[cache_key] = inline_serializer(
            name=f"PreConsultation{inner_serializer_class.__name__}Envelope",
            fields={
                "success": serializers.BooleanField(),
                "data": inner_serializer_class(),
            },
        )
    return _ENVELOPE_CACHE[cache_key]


def pre_consultation_conflict_envelope(
    session_response_serializer_class: Type[serializers.Serializer],
) -> Type[serializers.Serializer]:
    cache_key = f"conflict:{session_response_serializer_class.__name__}"
    if cache_key not in _ENVELOPE_CACHE:
        _ENVELOPE_CACHE[cache_key] = inline_serializer(
            name=f"PreConsultation{session_response_serializer_class.__name__}ConflictEnvelope",
            fields={
                "success": serializers.BooleanField(),
                "data": session_response_serializer_class(),
            },
        )
    return _ENVELOPE_CACHE[cache_key]


PreConsultationSessionConflictEnvelope = pre_consultation_conflict_envelope(
    PreConsultationSessionResponseSerializer
)


def filter_pre_consultation_endpoints(endpoints: list[tuple]) -> list[tuple]:
    return [
        endpoint
        for endpoint in endpoints
        if endpoint[0].startswith("/pre-consultation/")
    ]


def postprocess_pre_consultation_schema(
    result: dict,
    generator: object,
    request: object,
    public: bool,
) -> dict:
    paths = result.get("paths", {})
    ordered_paths = {
        path_key: paths[path_key]
        for path_key in PRE_CONSULTATION_PATH_ORDER
        if path_key in paths
    }
    result["paths"] = ordered_paths
    result["tags"] = [
        {
            "name": PRE_CONSULTATION_SESSION_TAG,
            "description": "Steps 1, 11–12: session start, result (health map), and complete.",
        },
        {
            "name": PRE_CONSULTATION_LAYER_TAG,
            "description": "Steps 2–10: wizard layers. Each layer: GET (load) then PUT (save).",
        },
    ]
    return result


def build_layer_get_description(layer_id: str) -> str:
    step = LAYER_EXECUTION_STEPS[layer_id]
    summary = LAYER_STEP_SUMMARIES[layer_id]
    return f"Step {step} — Load `{layer_id}` ({summary})."


def build_layer_put_description(layer_id: str) -> str:
    step = LAYER_EXECUTION_STEPS[layer_id]
    summary = LAYER_STEP_SUMMARIES[layer_id]
    extra = ""
    if layer_id == PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT:
        extra = " Returns `data.next_layer` for cluster-probe routing."
    elif layer_id == PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE:
        extra = " Skipped unless lifestyle routes here."
    elif layer_id == PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES:
        extra = " Advances current_layer to patient_health_map."
    return f"Step {step} — Save `{layer_id}` ({summary}).{extra}"


def generate_pre_consultation_openapi_schema() -> dict:
    from django.conf import settings
    from drf_spectacular.generators import SchemaGenerator

    spectacular_settings = settings.SPECTACULAR_SETTINGS
    original_values = {
        key: spectacular_settings.get(key)
        for key in PRE_CONSULTATION_SPECTACULAR_SETTINGS
    }
    spectacular_settings.update(PRE_CONSULTATION_SPECTACULAR_SETTINGS)
    generator = SchemaGenerator(
        title=PRE_CONSULTATION_OPENAPI_TITLE,
        version=spectacular_settings.get("VERSION", "1.0.0"),
    )
    schema = generator.get_schema(request=None, public=True)
    for key, value in original_values.items():
        if value is None:
            spectacular_settings.pop(key, None)
        else:
            spectacular_settings[key] = value
    return schema
