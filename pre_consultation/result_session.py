"""Load pre-consultation session + related data for result APIs keyed by user_id."""

from dataclasses import dataclass

from rest_framework.exceptions import NotFound

from accounts.customers.models import CustomerProfile
from pre_consultation.models import PreConsultationMedicalHistory, PreConsultationSession
from pre_consultation.utils.engine_directive import DirectiveCatalog, load_directive


@dataclass(frozen=True)
class ResultSessionContext:
    session: PreConsultationSession
    customer_profile: CustomerProfile | None
    medical_history: PreConsultationMedicalHistory | None
    catalog: DirectiveCatalog


def get_result_session_context(user_id: str) -> ResultSessionContext:
    session = (
        PreConsultationSession.objects.filter(user_id=user_id)
        .select_related("user", "artifacts")
        .prefetch_related(
            "category_selections",
            "concerns__symptoms",
            "concerns__sources",
            "concerns__family_history",
            "concerns__probe_answers",
            "preparation_checklist_items",
            "health_goals",
            "cluster_scores",
            "lifestyle_answers",
            "notes",
        )
        .first()
    )
    if session is None:
        raise NotFound("Pre-consultation session not found for this user.")

    customer_profile = (
        CustomerProfile.objects.filter(customer__user=session.user, is_main=True)
        .select_related("customer")
        .first()
    )
    medical_history = (
        PreConsultationMedicalHistory.objects.filter(session=session)
        .prefetch_related(
            "diagnoses",
            "medications",
            "surgeries",
            "sexual_health_answers",
            "medical_reports__summary",
        )
        .first()
    )
    return ResultSessionContext(
        session=session,
        customer_profile=customer_profile,
        medical_history=medical_history,
        catalog=load_directive(),
    )
