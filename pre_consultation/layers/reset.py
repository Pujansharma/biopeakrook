"""Cascade invalidation when a layer is edited or its upstream inputs change.

LAYER_DEPENDENTS defines the downstream layers to wipe; cluster scores are
deleted whenever concern, symptom, probe, or lifestyle data changes.
"""

from django.db import transaction

from pre_consultation.cluster_scoring import delete_session_cluster_scores
from pre_consultation.models import (
    PreConsultationCategorySelection,
    PreConsultationConcern,
    PreConsultationConcernFamilyHistory,
    PreConsultationConcernProbeAnswer,
    PreConsultationConcernSource,
    PreConsultationConcernSymptom,
    PreConsultationDiagnosis,
    PreConsultationHealthGoal,
    PreConsultationLifestyleAnswer,
    PreConsultationMedicalHistory,
    PreConsultationSession,
    PreConsultationSexualHealthAnswer,
)

from pre_consultation.utils.constants import PreConsultationLayerProgression

# Keys are edited layers; values are downstream layers whose stored answers
# become stale and must be cleared.
LAYER_DEPENDENTS: dict[str, list[str]] = {
    PreConsultationLayerProgression.PATIENT_CATEGORY: [
        PreConsultationLayerProgression.PATIENT_CONCERN,
        PreConsultationLayerProgression.PATIENT_SYMPTOM,
        PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
    PreConsultationLayerProgression.PATIENT_CONCERN: [
        PreConsultationLayerProgression.PATIENT_SYMPTOM,
        PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
    PreConsultationLayerProgression.PATIENT_SYMPTOM: [
        PreConsultationLayerProgression.PATIENT_CONCERN_PROBE,
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
    PreConsultationLayerProgression.PATIENT_CONCERN_PROBE: [
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
    PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT: [
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
    PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT: [
        PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE,
    ],
}


def reset_category_layer(session: PreConsultationSession) -> None:
    PreConsultationCategorySelection.objects.filter(session=session).delete()


def reset_concern_layer(session: PreConsultationSession) -> None:
    PreConsultationConcern.objects.filter(session=session).delete()
    delete_session_cluster_scores(session)


def reset_symptom_layer(session: PreConsultationSession) -> None:
    concern_ids = list(session.concerns.values_list("pk", flat=True))
    PreConsultationConcernSymptom.objects.filter(concern_id__in=concern_ids).delete()
    PreConsultationConcernSource.objects.filter(concern_id__in=concern_ids).delete()
    PreConsultationConcernFamilyHistory.objects.filter(
        concern_id__in=concern_ids
    ).delete()
    delete_session_cluster_scores(session)


def reset_concern_probe_layer(session: PreConsultationSession) -> None:
    session.concerns.update(
        functional_impact_id="",
        duration_impact_id="",
        progression_impact_id="",
        confidence_score=0,
        probe_flagged=False,
    )
    delete_session_cluster_scores(session)


def reset_cluster_probe_layer(session: PreConsultationSession) -> None:
    concern_ids = list(session.concerns.values_list("pk", flat=True))
    PreConsultationConcernProbeAnswer.objects.filter(
        concern_id__in=concern_ids
    ).delete()
    session.concerns.update(
        probe_question_count=0,
        probe_positive_count=0,
    )
    delete_session_cluster_scores(session)


def reset_lifestyle_layer(session: PreConsultationSession) -> None:
    PreConsultationLifestyleAnswer.objects.filter(session=session).delete()
    delete_session_cluster_scores(session)


def reset_goals_layer(session: PreConsultationSession) -> None:
    PreConsultationHealthGoal.objects.filter(session=session).delete()


LAYER_RESET_HANDLERS = {
    PreConsultationLayerProgression.PATIENT_CATEGORY: reset_category_layer,
    PreConsultationLayerProgression.PATIENT_CONCERN: reset_concern_layer,
    PreConsultationLayerProgression.PATIENT_SYMPTOM: reset_symptom_layer,
    PreConsultationLayerProgression.PATIENT_CONCERN_PROBE: reset_concern_probe_layer,
    PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE: reset_cluster_probe_layer,
    PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT: reset_lifestyle_layer,
    PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES: reset_goals_layer,
}


def reset_layer(session: PreConsultationSession, layer_id: str) -> None:
    reset_handler = LAYER_RESET_HANDLERS.get(layer_id)
    if reset_handler is not None:
        reset_handler(session)


def reset_dependent_layers(session: PreConsultationSession, layer_id: str) -> None:
    for dependent_layer_id in LAYER_DEPENDENTS.get(layer_id, []):
        reset_layer(session, dependent_layer_id)


def reset_gender_dependent_medical_history(session: PreConsultationSession) -> None:
    """Clear reproductive diagnoses and sexual-health answers after gender change."""
    medical_history = PreConsultationMedicalHistory.objects.filter(
        session=session
    ).first()
    if medical_history is None:
        return
    PreConsultationDiagnosis.objects.filter(
        medical_history=medical_history,
        is_reproductive=True,
    ).delete()
    PreConsultationSexualHealthAnswer.objects.filter(
        medical_history=medical_history,
    ).delete()


def reset_dependent_layers_in_transaction(
    session: PreConsultationSession,
    layer_id: str,
) -> None:
    with transaction.atomic():
        reset_dependent_layers(session, layer_id)
