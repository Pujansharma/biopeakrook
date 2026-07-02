from dataclasses import dataclass
from typing import Type

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from core.utils.view_types import GetMethodMixin, PutMethodMixin
from core.utils.views import BaseGenericAPIView
from pre_consultation.layer_execution import execute_layer_get, execute_layer_put
from pre_consultation.layers.base import LayerHandler
from pre_consultation.layers.registry import LAYER_HANDLERS
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.layers.patient_goals_priorities import (
    PatientGoalsPrioritiesGoalRequestSerializer,
)
from pre_consultation.utils.schema import (
    CUSTOMER_PROFILE_HEADER,
    PRE_CONSULTATION_LAYER_TAG,
    PatientLifestyleEnvironmentPutRequestSerializer,
    PreConsultationEmptySuccessSerializer,
    PreConsultationLayerNotImplementedSerializer,
    PreConsultationSessionConflictEnvelope,
    build_layer_get_description,
    build_layer_put_description,
    pre_consultation_data_envelope,
)
from pre_consultation.utils.throttling import (
    PreConsultationGetThrottle,
    PreConsultationPutThrottle,
)


@dataclass(frozen=True)
class LayerViewDefinition:
    layer_id: str
    view_class_name: str


LAYER_VIEW_DEFINITIONS: tuple[LayerViewDefinition, ...] = (
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_BASELINE,
        "PatientBaselineLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_CATEGORY,
        "PatientCategoryLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_CONCERN,
        "PatientConcernLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_SYMPTOM,
        "PatientSymptomLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
        "PatientConcernProbeLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
        "PatientClusterProbeLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT,
        "PatientLifestyleEnvironmentLayerView",
    ),
    LayerViewDefinition(
        PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES,
        "PatientGoalsPrioritiesLayerView",
    ),
)


def build_put_responses(layer_handler: LayerHandler) -> dict:
    put_responses = {
        409: PreConsultationSessionConflictEnvelope,
        501: PreConsultationLayerNotImplementedSerializer,
    }
    if layer_handler.put_includes_data:
        put_response_class = (
            layer_handler.put_response_serializer_class
            or layer_handler.response_serializer_class
        )
        put_responses[200] = pre_consultation_data_envelope(put_response_class)
    else:
        put_responses[200] = PreConsultationEmptySuccessSerializer
    return put_responses


def resolve_put_request_schema(
    layer_id: str,
    layer_handler: LayerHandler,
) -> Type[serializers.Serializer]:
    if layer_id == PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES:
        return PatientGoalsPrioritiesGoalRequestSerializer(many=True)
    if layer_id == PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT:
        return PatientLifestyleEnvironmentPutRequestSerializer
    return layer_handler.request_serializer_class


def build_layer_view_class(definition: LayerViewDefinition) -> type:
    handler = LAYER_HANDLERS[definition.layer_id]
    parameters = []
    if handler.needs_customer_profile:
        parameters.append(CUSTOMER_PROFILE_HEADER)

    get_response = pre_consultation_data_envelope(handler.response_serializer_class)
    put_responses = build_put_responses(handler)
    put_request = resolve_put_request_schema(definition.layer_id, handler)

    class LayerView(BaseGenericAPIView, GetMethodMixin, PutMethodMixin):
        permission_classes = [IsAuthenticated]
        throttle_classes = [PreConsultationGetThrottle, PreConsultationPutThrottle]

        def get(self, request, *args, **kwargs):
            return execute_layer_get(request, handler)

        def put(self, request, *args, **kwargs):
            return execute_layer_put(request, handler)

    decorated_view = extend_schema_view(
        get=extend_schema(
            tags=[PRE_CONSULTATION_LAYER_TAG],
            parameters=parameters,
            description=build_layer_get_description(definition.layer_id),
            responses={200: get_response},
        ),
        put=extend_schema(
            tags=[PRE_CONSULTATION_LAYER_TAG],
            parameters=parameters,
            description=build_layer_put_description(definition.layer_id),
            request=put_request,
            responses=put_responses,
        ),
    )(LayerView)
    decorated_view.__name__ = definition.view_class_name
    decorated_view.__qualname__ = definition.view_class_name
    return decorated_view


def build_layer_view_registry() -> dict[str, type]:
    return {
        definition.view_class_name: build_layer_view_class(definition)
        for definition in LAYER_VIEW_DEFINITIONS
    }


_LAYER_VIEW_REGISTRY = build_layer_view_registry()

PatientBaselineLayerView = _LAYER_VIEW_REGISTRY["PatientBaselineLayerView"]
PatientCategoryLayerView = _LAYER_VIEW_REGISTRY["PatientCategoryLayerView"]
PatientConcernLayerView = _LAYER_VIEW_REGISTRY["PatientConcernLayerView"]
PatientSymptomLayerView = _LAYER_VIEW_REGISTRY["PatientSymptomLayerView"]
PatientConcernProbeLayerView = _LAYER_VIEW_REGISTRY["PatientConcernProbeLayerView"]
PatientClusterProbeLayerView = _LAYER_VIEW_REGISTRY["PatientClusterProbeLayerView"]
PatientLifestyleEnvironmentLayerView = _LAYER_VIEW_REGISTRY[
    "PatientLifestyleEnvironmentLayerView"
]
PatientGoalsPrioritiesLayerView = _LAYER_VIEW_REGISTRY[
    "PatientGoalsPrioritiesLayerView"
]

__all__ = [
    "PatientBaselineLayerView",
    "PatientCategoryLayerView",
    "PatientConcernLayerView",
    "PatientSymptomLayerView",
    "PatientConcernProbeLayerView",
    "PatientClusterProbeLayerView",
    "PatientLifestyleEnvironmentLayerView",
    "PatientGoalsPrioritiesLayerView",
]
