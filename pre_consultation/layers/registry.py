"""Maps PreConsultationLayerProgression values to fully wired LayerHandler instances."""

from pre_consultation.layers.base import LayerHandler
from pre_consultation.layers.patient_baseline import (
    PatientBaselineRequestSerializer,
    PatientBaselineResponseSerializer,
    PatientBaselineV2RequestSerializer,
    PatientBaselineV2ResponseSerializer,
    load_patient_baseline_payload,
    load_patient_baseline_v2_payload,
    persist_patient_baseline_payload,
    persist_patient_baseline_v2_payload,
)
from pre_consultation.layers.patient_category import (
    PatientCategoryRequestSerializer,
    PatientCategoryResponseSerializer,
    load_patient_category_payload,
    persist_patient_category_payload,
)
from pre_consultation.layers.patient_concern import (
    PatientConcernRequestSerializer,
    PatientConcernResponseSerializer,
    build_patient_concern_put_context,
    load_patient_concern_payload,
    persist_patient_concern_payload,
    persist_patient_concern_v2_payload,
)
from pre_consultation.layers.patient_concern_probe import (
    PatientConcernProbeRequestSerializer,
    PatientConcernProbeResponseSerializer,
    build_patient_concern_probe_put_context,
    load_patient_concern_probe_payload,
    persist_patient_concern_probe_payload,
)
from pre_consultation.layers.patient_goals_priorities import (
    PatientGoalsPrioritiesRequestSerializer,
    PatientGoalsPrioritiesResponseSerializer,
    PatientGoalsPrioritiesV2ResponseSerializer,
    load_patient_goals_priorities_payload,
    load_patient_goals_priorities_v2_payload,
    persist_patient_goals_priorities_payload,
    persist_patient_goals_priorities_v2_payload,
)
from pre_consultation.layers.patient_lifestyle_environment import (
    PatientLifestyleEnvironmentPutResponseSerializer,
    PatientLifestyleEnvironmentRequestSerializer,
    PatientLifestyleEnvironmentResponseSerializer,
    load_patient_lifestyle_environment_payload,
    load_patient_lifestyle_environment_put_payload,
    load_patient_lifestyle_environment_v2_put_payload,
    persist_patient_lifestyle_environment_payload,
    persist_patient_lifestyle_environment_v2_payload,
)
from pre_consultation.layers.patient_medical_history_context import (
    PatientMedicalHistoryContextRequestSerializer,
    PatientMedicalHistoryContextResponseSerializer,
    build_patient_medical_history_put_context,
    load_patient_medical_history_context_payload,
    persist_patient_medical_history_context_payload,
)
from pre_consultation.layers.patient_cluster_probe import (
    PatientClusterProbeRequestSerializer,
    PatientClusterProbeResponseSerializer,
    build_patient_cluster_probe_put_context,
    load_patient_cluster_probe_payload,
    persist_patient_cluster_probe_payload,
    persist_patient_cluster_probe_v2_payload,
)
from pre_consultation.layers.patient_concern_probe_v2 import (
    PatientConcernProbeV2RequestSerializer,
    PatientConcernProbeV2ResponseSerializer,
    build_patient_concern_probe_v2_put_context,
    load_patient_concern_probe_v2_payload,
    persist_patient_concern_probe_v2_payload,
)
from pre_consultation.layers.patient_symptom import (
    PatientSymptomRequestSerializer,
    PatientSymptomResponseSerializer,
    build_patient_symptom_put_context,
    load_patient_symptom_payload,
    persist_patient_symptom_payload,
)
from pre_consultation.utils.constants import PreConsultationLayerProgression

LAYER_HANDLERS: dict[str, LayerHandler] = {
    layer_progression.value: LayerHandler(layer_id=layer_progression.value)
    for layer_progression in PreConsultationLayerProgression
}

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_BASELINE] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_BASELINE,
    request_serializer_class=PatientBaselineRequestSerializer,
    response_serializer_class=PatientBaselineResponseSerializer,
    load_payload=load_patient_baseline_payload,
    persist_payload=persist_patient_baseline_payload,
    needs_customer_profile=True,
    put_includes_data=False,
)

PATIENT_BASELINE_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_BASELINE,
    request_serializer_class=PatientBaselineV2RequestSerializer,
    response_serializer_class=PatientBaselineV2ResponseSerializer,
    load_payload=load_patient_baseline_v2_payload,
    persist_payload=persist_patient_baseline_v2_payload,
    needs_customer_profile=True,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_CATEGORY] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CATEGORY,
    request_serializer_class=PatientCategoryRequestSerializer,
    response_serializer_class=PatientCategoryResponseSerializer,
    load_payload=load_patient_category_payload,
    persist_payload=persist_patient_category_payload,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_CONCERN] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CONCERN,
    request_serializer_class=PatientConcernRequestSerializer,
    response_serializer_class=PatientConcernResponseSerializer,
    load_payload=load_patient_concern_payload,
    persist_payload=persist_patient_concern_payload,
    build_put_serializer_context=build_patient_concern_put_context,
    put_includes_data=False,
)

PATIENT_CONCERN_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CONCERN,
    request_serializer_class=PatientConcernRequestSerializer,
    response_serializer_class=PatientConcernResponseSerializer,
    load_payload=load_patient_concern_payload,
    persist_payload=persist_patient_concern_v2_payload,
    build_put_serializer_context=build_patient_concern_put_context,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_SYMPTOM] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_SYMPTOM,
    request_serializer_class=PatientSymptomRequestSerializer,
    response_serializer_class=PatientSymptomResponseSerializer,
    load_payload=load_patient_symptom_payload,
    persist_payload=persist_patient_symptom_payload,
    build_put_serializer_context=build_patient_symptom_put_context,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_CONCERN_PROBE] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
    request_serializer_class=PatientConcernProbeRequestSerializer,
    response_serializer_class=PatientConcernProbeResponseSerializer,
    load_payload=load_patient_concern_probe_payload,
    persist_payload=persist_patient_concern_probe_payload,
    build_put_serializer_context=build_patient_concern_probe_put_context,
    put_includes_data=False,
)

PATIENT_CONCERN_PROBE_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
    request_serializer_class=PatientConcernProbeV2RequestSerializer,
    response_serializer_class=PatientConcernProbeV2ResponseSerializer,
    load_payload=load_patient_concern_probe_v2_payload,
    persist_payload=persist_patient_concern_probe_v2_payload,
    build_put_serializer_context=build_patient_concern_probe_v2_put_context,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    request_serializer_class=PatientClusterProbeRequestSerializer,
    response_serializer_class=PatientClusterProbeResponseSerializer,
    load_payload=load_patient_cluster_probe_payload,
    persist_payload=persist_patient_cluster_probe_payload,
    build_put_serializer_context=build_patient_cluster_probe_put_context,
    put_includes_data=False,
)

PATIENT_CLUSTER_PROBE_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    request_serializer_class=PatientClusterProbeRequestSerializer,
    response_serializer_class=PatientClusterProbeResponseSerializer,
    load_payload=load_patient_cluster_probe_payload,
    persist_payload=persist_patient_cluster_probe_v2_payload,
    build_put_serializer_context=build_patient_cluster_probe_put_context,
    put_includes_data=False,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT] = (
    LayerHandler(
        layer_id=PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT,
        request_serializer_class=PatientMedicalHistoryContextRequestSerializer,
        response_serializer_class=PatientMedicalHistoryContextResponseSerializer,
        load_payload=load_patient_medical_history_context_payload,
        persist_payload=persist_patient_medical_history_context_payload,
        build_put_serializer_context=build_patient_medical_history_put_context,
        needs_customer_profile=True,
        put_includes_data=False,
    )
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT] = (
    LayerHandler(
        layer_id=PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT,
        request_serializer_class=PatientLifestyleEnvironmentRequestSerializer,
        response_serializer_class=PatientLifestyleEnvironmentResponseSerializer,
        put_response_serializer_class=PatientLifestyleEnvironmentPutResponseSerializer,
        load_payload=load_patient_lifestyle_environment_payload,
        load_put_payload=load_patient_lifestyle_environment_put_payload,
        persist_payload=persist_patient_lifestyle_environment_payload,
        put_includes_data=True,
    )
)

PATIENT_LIFESTYLE_ENVIRONMENT_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT,
    request_serializer_class=PatientLifestyleEnvironmentRequestSerializer,
    response_serializer_class=PatientLifestyleEnvironmentResponseSerializer,
    put_response_serializer_class=PatientLifestyleEnvironmentPutResponseSerializer,
    load_payload=load_patient_lifestyle_environment_payload,
    load_put_payload=load_patient_lifestyle_environment_v2_put_payload,
    persist_payload=persist_patient_lifestyle_environment_v2_payload,
    put_includes_data=True,
)

LAYER_HANDLERS[PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES] = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES,
    request_serializer_class=PatientGoalsPrioritiesRequestSerializer,
    response_serializer_class=PatientGoalsPrioritiesResponseSerializer,
    load_payload=load_patient_goals_priorities_payload,
    persist_payload=persist_patient_goals_priorities_payload,
    put_includes_data=False,
)

PATIENT_GOALS_PRIORITIES_V2_HANDLER = LayerHandler(
    layer_id=PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES,
    request_serializer_class=PatientGoalsPrioritiesRequestSerializer,
    response_serializer_class=PatientGoalsPrioritiesV2ResponseSerializer,
    load_payload=load_patient_goals_priorities_v2_payload,
    persist_payload=persist_patient_goals_priorities_v2_payload,
    put_includes_data=False,
)


def get_layer_handler(layer_id: str) -> LayerHandler | None:
    return LAYER_HANDLERS.get(layer_id)
