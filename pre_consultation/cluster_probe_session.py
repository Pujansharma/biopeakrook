"""Cluster probe eligibility for lifestyle layer routing."""

from pre_consultation.layers.patient_cluster_probe import (
    get_cluster_probe_eligible_concern_ids,
)
from pre_consultation.models import PreConsultationSession


def session_requires_cluster_probe(session: PreConsultationSession) -> bool:
    return bool(get_cluster_probe_eligible_concern_ids(session))
