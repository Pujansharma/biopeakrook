"""LLM configuration for the preconsultation module.

Each task that calls an LLM has its own named config entry so models can be
swapped independently. Callers can override any field by passing kwargs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskLLMConfig:
    model: str
    temperature: float = 0.0
    # Client-side retries with exponential backoff for transient failures
    # (429 rate limits, timeouts, upstream 5xx). Does NOT help terminal errors
    # like insufficient_quota or auth — those still surface after the retries.
    max_retries: int = 3
    # Extra kwargs forwarded verbatim to ChatOpenAI (e.g. max_tokens); override
    # max_retries here per task if needed.
    extra: dict = field(default_factory=dict)


# One entry per LLM-calling function. Add a new entry when a new LLM call is
# introduced; adjust the model/temperature here without touching call sites.
TASK_CONFIGS: dict[str, TaskLLMConfig] = {
    # summarize_patient: produces the two prose summaries.
    "summarize_patient": TaskLLMConfig(
        model="gpt-5-mini",
        temperature=0.0,
    ),
    # generate_checklist: produces probe hypotheses with reasons.
    "generate_checklist": TaskLLMConfig(
        model="gpt-5-mini",
        temperature=0.0,
    ),
    # read_image: transcribes embedded images / scans / charts into text.
    "read_image": TaskLLMConfig(
        model="gpt-5-mini",
        temperature=0.0,
    ),
    # extract_insights: pulls patient-specific insights from one report page.
    "extract_insights": TaskLLMConfig(
        model="gpt-5-mini",
        temperature=0.0,
    ),
    # consolidate_insights: groups raw per-page facts into dense doctor-facing insights.
    "consolidate_insights": TaskLLMConfig(
        model="gpt-5.2",
        temperature=0.0,
    ),
    # extract_document_metadata: pulls document-level creation date + issuing
    # facility from the opening pages (works for any document, not just reports).
    "extract_document_metadata": TaskLLMConfig(
        model="gpt-5-mini",
        temperature=0.0,
    ),
}
