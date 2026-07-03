"""Session lookup helpers shared by views and layer execution."""

from rest_framework.exceptions import NotFound

from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import PreConsultationSessionStatus


def get_user_pre_consultation_session(user) -> PreConsultationSession:
    session = PreConsultationSession.objects.filter(user=user).first()
    if session is None:
        raise NotFound("Pre-consultation session not found.")
    return session


def is_session_completed(session: PreConsultationSession) -> bool:
    return session.status == PreConsultationSessionStatus.COMPLETED
