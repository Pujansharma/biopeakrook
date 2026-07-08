"""Background worker for LLM-based medical report insight extraction.

Persistence for extraction results is not wired up yet — results are only
logged so the flow can be exercised end-to-end.
"""

import logging
import threading

from django.db import connections

from intelligence_engine.preconsultation import extract_insights_batch

logger = logging.getLogger(__name__)


def spawn_report_insights_extraction(session_id: str, user_id: str) -> None:
    """Spawn background daemon thread to run report insight extraction (non-blocking)."""
    thread = threading.Thread(
        target=_run_report_insights_extraction,
        args=(session_id, user_id),
        daemon=True,
    )
    thread.start()


def _run_report_insights_extraction(session_id: str, user_id: str) -> None:
    """Background thread target: fetch uploaded reports, call LLM, log results."""
    try:
        from pre_consultation.result_session import get_result_session_context
        from pre_consultation.translate_payload import (
            build_extract_insights_reports,
        )

        context = get_result_session_context(user_id)
        reports = build_extract_insights_reports(context)

        if not reports:
            logger.info(
                f"No medical reports to extract for session {session_id}",
                extra={"session_id": session_id},
            )
            return

        result = extract_insights_batch(reports)

        logger.info(
            f"Report insight extraction completed for session {session_id}: "
            f"{len(result.get('results', []))} processed, "
            f"{len(result.get('skipped', []))} skipped",
            extra={"session_id": session_id, "result": result},
        )

    except Exception as e:
        logger.exception(
            f"Report insight extraction failed for session {session_id}: {str(e)}",
            extra={"session_id": session_id},
        )

    finally:
        connections.close_all()
