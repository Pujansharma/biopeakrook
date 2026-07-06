"""Typed errors for the preconsultation module.

Callers (a DRF view, a background job) need to tell apart bad input
(`ValueError`, raised by validation, a client 4xx) from a pipeline failure.
The pipeline wraps any failure at its boundary in a `PreconsultationError`
carrying the `stage` it failed in, the `client_id`, and the original
underlying exception as `cause` so the real error is never swallowed.

Retries for transient failures (rate limits, timeouts, upstream 5xx) are
handled by the LLM client itself (`max_retries` in `TaskLLMConfig`) — once
those are exhausted, the failure is terminal from the caller's perspective and
is raised as-is.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PreconsultationError(Exception):
    """Base for all typed preconsultation failures.

    Attributes:
      stage:     which pipeline step failed (e.g. "summaries", "checklist").
      client_id: the patient_baseline.id, for correlation in logs/queues.
      cause:     the original underlying exception.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        client_id: str = "",
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.client_id = client_id
        self.cause = cause


class SummaryGenerationError(PreconsultationError):
    """A summarize_patient stage failed (LLM call, reorder, or preprocessing)."""
