"""Background worker for LLM-based pre-consultation summarization."""

import logging
import threading
from django.db import connections
from django.utils import timezone

from intelligence_engine.preconsultation import summarize_patient
from pre_consultation.models import (
    PreConsultationSession,
    PreConsultationSessionArtifacts,
    PreConsultationPreparationChecklistItem,
)
from pre_consultation.utils.constants import (
    PreConsultationArtifactGenerationStatus,
)

logger = logging.getLogger(__name__)


def spawn_summarization(session_id: str, user_id: str) -> None:
    """Spawn background daemon thread to run summarization (non-blocking)."""
    thread = threading.Thread(
        target=_run_summarization,
        args=(session_id, user_id),
        daemon=True,
    )
    thread.start()


def _run_summarization(session_id: str, user_id: str) -> None:
    """Background thread target: fetch session, call LLM, persist results."""
    try:
        session = PreConsultationSession.objects.get(
            pk=session_id, user_id=user_id
        )

        artifacts, _ = PreConsultationSessionArtifacts.objects.get_or_create(
            session=session
        )
        artifacts.generation_status = (
            PreConsultationArtifactGenerationStatus.IN_PROGRESS
        )
        artifacts.generation_started_at = timezone.now()
        artifacts.save(
            update_fields=[
                "generation_status",
                "generation_started_at",
                "updated_at",
            ]
        )

        from pre_consultation.result_session import get_result_session_context
        from pre_consultation.translate_payload import (
            build_summarize_client_details,
        )

        context = get_result_session_context(user_id)
        client_details = build_summarize_client_details(context)

        result = summarize_patient(client_details, trigger_webhook=True)

        _persist_summarization_result(session, artifacts, result)

        logger.info(
            f"Summarization completed for session {session_id}",
            extra={"session_id": session_id},
        )

    except Exception as e:
        logger.exception(
            f"Summarization failed for session {session_id}: {str(e)}",
            extra={"session_id": session_id},
        )
        try:
            session = PreConsultationSession.objects.get(pk=session_id)
            artifacts = PreConsultationSessionArtifacts.objects.get(
                session=session
            )
            artifacts.generation_status = (
                PreConsultationArtifactGenerationStatus.FAILED
            )
            artifacts.generation_completed_at = timezone.now()
            artifacts.save(
                update_fields=[
                    "generation_status",
                    "generation_completed_at",
                    "updated_at",
                ]
            )
        except Exception as persist_error:
            logger.exception(
                f"Failed to mark artifacts as FAILED: {str(persist_error)}"
            )

    finally:
        connections.close_all()


def _persist_summarization_result(
    session: PreConsultationSession,
    artifacts: PreConsultationSessionArtifacts,
    result: dict,
) -> None:
    """Persist LLM result to artifacts and checklist tables."""
    summary = result.get("preconsultation_summary", "")
    family_risk_summary = result.get("family_risk_summary", "")
    checklist_items = result.get("preconsultation_checklist", [])

    artifacts.summary = summary
    artifacts.quick_summary = summary
    artifacts.family_risk_summary = family_risk_summary
    artifacts.generation_status = (
        PreConsultationArtifactGenerationStatus.COMPLETED
    )
    artifacts.generation_completed_at = timezone.now()
    artifacts.save(
        update_fields=[
            "summary",
            "quick_summary",
            "family_risk_summary",
            "generation_status",
            "generation_completed_at",
            "updated_at",
        ]
    )

    PreConsultationPreparationChecklistItem.objects.filter(
        session=session
    ).delete()

    checklist_rows = [
        PreConsultationPreparationChecklistItem(
            session=session,
            identified_concern=item.get("probe", ""),
            marked=False,
        )
        for item in checklist_items
    ]

    PreConsultationPreparationChecklistItem.objects.bulk_create(checklist_rows)
