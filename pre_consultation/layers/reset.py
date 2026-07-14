"""Targeted parent-child invalidation (diff-driven, not blanket layer wipe)."""

from django.utils import timezone

from pre_consultation.models import (
    PreConsultationConcern,
    PreConsultationConcernProbeAnswer,
    PreConsultationDiagnosis,
    PreConsultationMedicalHistory,
    PreConsultationSession,
    PreConsultationSexualHealthAnswer,
)
from pre_consultation.utils.directive import get_concern_category_id_map


def clear_session_cluster_probe_answers(session: PreConsultationSession) -> None:
    """Clear prior cluster-probe answers so lifestyle can rescore from provisional only."""
    PreConsultationConcernProbeAnswer.objects.filter(concern__session=session).delete()
    session.concerns.update(
        probe_question_count=0,
        probe_positive_count=0,
        updated_at=timezone.now(),
    )


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


def delete_concerns_for_deselected_categories(
    session: PreConsultationSession,
    selected_category_ids: list[str],
) -> None:
    """Remove concerns whose category is no longer selected (FK cascade on children)."""
    selected_category_id_set = set(selected_category_ids)
    concern_category_id_map = get_concern_category_id_map()
    orphan_concern_ids = [
        concern.concern_id
        for concern in session.concerns.only("concern_id")
        if concern_category_id_map[concern.concern_id]
        not in selected_category_id_set
    ]
    if not orphan_concern_ids:
        return
    PreConsultationConcern.objects.filter(
        session=session,
        concern_id__in=orphan_concern_ids,
    ).delete()
