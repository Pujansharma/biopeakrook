"""Shared ORM queries for layer handlers and scoring engines."""

from django.db.models import QuerySet

from pre_consultation.models import (
    PreConsultationConcern,
    PreConsultationMedicalHistory,
    PreConsultationSession,
)
from pre_consultation.utils.directive import (
    get_diagnosis_override_concern_ids_by_diagnosis_id,
)


def get_session_category_ids(session: PreConsultationSession) -> set[str]:
    return set(session.category_selections.values_list("category_id", flat=True))


def get_session_concern_ids(session: PreConsultationSession) -> set[str]:
    return set(session.concerns.values_list("concern_id", flat=True))


def get_session_concerns_ordered(
    session: PreConsultationSession,
) -> QuerySet[PreConsultationConcern]:
    return session.concerns.order_by("created_at")


def get_or_create_medical_history(
    session: PreConsultationSession,
) -> PreConsultationMedicalHistory:
    medical_history, _created = PreConsultationMedicalHistory.objects.get_or_create(
        session=session,
    )
    return medical_history


def get_concern_by_id(
    session: PreConsultationSession,
    concern_id: str,
) -> PreConsultationConcern | None:
    return session.concerns.filter(concern_id=concern_id).first()


def get_medical_override_concern_ids(session: PreConsultationSession) -> set[str]:
    """Diagnosis selections that force a concern confidence floor via directive."""
    medical_history = PreConsultationMedicalHistory.objects.filter(
        session=session,
    ).first()
    if medical_history is None:
        return set()

    selected_diagnosis_ids = set(
        medical_history.diagnoses.filter(is_reproductive=False).values_list(
            "diagnosis_id",
            flat=True,
        )
    )
    override_concern_ids_by_diagnosis_id = (
        get_diagnosis_override_concern_ids_by_diagnosis_id()
    )
    medical_override_concern_ids: set[str] = set()
    for diagnosis_id in selected_diagnosis_ids:
        medical_override_concern_ids.update(
            override_concern_ids_by_diagnosis_id.get(diagnosis_id, [])
        )
    return medical_override_concern_ids
