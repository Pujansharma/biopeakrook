"""Reconcile cluster scores and layer progression after upstream edits."""

from django.utils import timezone

from pre_consultation.cluster_scoring import persist_session_cluster_scores
from pre_consultation.layers.patient_cluster_probe import (
    get_cluster_probe_eligible_concern_ids,
)
from pre_consultation.layers.patient_lifestyle_environment import (
    get_session_lifestyle_answers,
)
from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import PreConsultationLayerProgression


def session_requires_cluster_probe(session: PreConsultationSession) -> bool:
    return bool(get_cluster_probe_eligible_concern_ids(session))


def sync_session_cluster_scores_from_lifestyle(
    session: PreConsultationSession,
) -> None:
    lifestyle_answers = get_session_lifestyle_answers(session)
    if lifestyle_answers:
        persist_session_cluster_scores(session, lifestyle_answers)


def reconcile_cluster_probe_progression(session: PreConsultationSession) -> None:
    sync_session_cluster_scores_from_lifestyle(session)
    if session.current_layer != PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE:
        return
    if session_requires_cluster_probe(session):
        return
    session.current_layer = PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES
    session.updated_at = timezone.now()
    session.save(update_fields=["current_layer", "updated_at"])
