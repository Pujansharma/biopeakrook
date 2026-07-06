"""Orchestration: pre-consultation form -> three doctor-facing summaries."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import date
from time import perf_counter
from typing import Literal

import requests
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from intelligence_engine.preconsultation import prompts
from intelligence_engine.preconsultation.llm import build_llm
from intelligence_engine.preconsultation.errors import SummaryGenerationError
from intelligence_engine.preconsultation.timing import elapsed_ms, log_stage
from intelligence_engine.preconsultation.langfuse_util import (
    build_client,
    patient_trace_span,
    run_metadata,
)
from intelligence_engine.preconsultation.validation import validate_summary_input
from intelligence_engine.preconsultation.salience import (
    WELLNESS,
    build_full_profile,
    checklist_seeds,
    family_risk_priority,
    has_family_history,
    patient_mode,
    summary_priority,
)

logger = logging.getLogger(__name__)

LANGFUSE_ENVIRONMENT = "onboarding-summary"


def _run_config(callbacks: list | None) -> dict:
    """LangChain invoke config: the callbacks plus the langfuse reserved run keys
    (user_id/session_id/tags/metadata) stashed on the handler, so summary runs are
    grouped and filterable by client_id exactly like the extraction runs."""
    cbs = callbacks or []
    config: dict = {"callbacks": cbs}
    meta = run_metadata(cbs[0] if cbs else None)
    if meta:
        config["metadata"] = meta
    return config


async def _run_llm(stage: str, client_id: str, coro):
    """Await one LLM call, log its latency, and (fail-whole) convert any
    provider/parse failure into a typed SummaryGenerationError carrying the
    stage, client_id, and the original exception as `cause`, so the first
    failing stage aborts the run with an error the caller can inspect.

    Retries for transient failures already happened inside the LLM client
    (`max_retries` in TaskLLMConfig) before this ever raises."""
    start = perf_counter()
    try:
        result = await coro
    except Exception as exc:
        logger.warning(
            "[timing] llm:%s FAILED after %.0fms client=%s: %s",
            stage,
            elapsed_ms(start),
            client_id,
            exc,
        )
        raise SummaryGenerationError(
            f"{stage} LLM call failed: {exc}",
            stage=stage,
            client_id=client_id,
            cause=exc,
        ) from exc
    logger.info(
        "[timing] llm:%s %.0fms client=%s", stage, elapsed_ms(start), client_id
    )
    return result


WEBHOOK_URL = os.environ["TOOLS_URL"] + os.environ["PRECONS_TOOL_TRIGGER_API"]

# Concern-mode axes: a node with pressing findings may warrant probing here.
# Ordered by clinical urgency (see _CONCERN_TAG_WEIGHT).
ConcernTag = Literal[
    "red_flag_escalation",
    "contradiction_resolution",
    "factual_discrepancy",
    "risk_refinement",
    "treatment_efficacy",
    "diagnostic_clarification",
    "missing_context",
    "medication_adherence",
    "lifestyle_driver",
]

# Wellness-mode axes: proactive directions for a broadly healthy patient.
WellnessTag = Literal[
    "factual_discrepancy",
    "preventive_screening",
    "early_risk_surveillance",
    "baseline_establishment",
    "lifestyle_optimization",
    "goal_alignment",
]

# Per-tag importance weight (INTERNAL — never exposed on ChecklistProbe). A
# moderate multiplier on the score so clinically urgent axes float toward the
# top of the checklist, while a very strong probe in a lower-weight tag can
# still outrank a weak probe in a higher-weight one. Tune these freely.
_CONCERN_TAG_WEIGHT: dict[str, float] = {
    "red_flag_escalation": 1.00,
    "contradiction_resolution": 0.95,
    "factual_discrepancy": 0.90,
    "risk_refinement": 0.85,
    "treatment_efficacy": 0.80,
    "diagnostic_clarification": 0.70,
    "missing_context": 0.65,
    "medication_adherence": 0.60,
    "lifestyle_driver": 0.55,
}
_WELLNESS_TAG_WEIGHT: dict[str, float] = {
    "factual_discrepancy": 0.90,
    "preventive_screening": 1.00,
    "early_risk_surveillance": 0.80,
    "baseline_establishment": 0.65,
    "lifestyle_optimization": 0.60,
    "goal_alignment": 0.55,
}
# Merged lookup used by scoring; default for any unmapped/paraphrased tag.
_TAG_WEIGHT: dict[str, float] = {**_CONCERN_TAG_WEIGHT, **_WELLNESS_TAG_WEIGHT}
_DEFAULT_TAG_WEIGHT = 0.5

# Intra-tag rank decay: within a tag, each successive hypothesis (after the
# strongest) is discounted by this factor ** rank, so one prolific tag can't
# monopolize the top of the checklist and bury other tags' best probes.
_TAG_RANK_DECAY = 0.6


class _HypothesisBase(BaseModel):
    """Shared fields for an LLM probe hypothesis (tag added per mode)."""

    probability: float = Field(
        description="0.0-1.0 estimate that this probe is warranted and will surface something clinically useful.",
        ge=0.0,
        le=1.0,
    )
    probe: str = Field(
        description="Short imperative direction for the doctor, e.g. 'Validate metabolic drivers'."
    )
    reason: str = Field(
        description="One or two sentences explaining why this probe is warranted — what clinical concern or data signal justifies it."
    )


class ConcernHypothesis(_HypothesisBase):
    tag: ConcernTag = Field(
        description="Which concern-mode probing axis this hypothesis falls under."
    )


class WellnessHypothesis(_HypothesisBase):
    tag: WellnessTag = Field(
        description="Which wellness-mode probing axis this hypothesis falls under."
    )


class ChecklistProbe(BaseModel):
    """A scored probe direction returned to the doctor as the checklist."""

    probe: str
    tag: str
    score: float
    reason: str


class _SummaryLLMOutput(BaseModel):
    """Raw structured output from the summaries LLM call."""

    preconsultation_summary: str = Field(
        description="Who the patient is, as a single dense prose paragraph, most critical findings first."
    )
    family_risk_summary: str = Field(
        description="Hereditary signals in the family history, cross-referenced with the patient's current patterns."
    )


class _ReorderedSummary(BaseModel):
    """Raw structured output from a reorder pass: the same prose, re-sequenced
    most-critical-first, with wording and register preserved."""

    summary: str = Field(
        description="The same summary content, reordered by priority, with wording, facts, and register unchanged."
    )


class _ConcernChecklistLLMOutput(BaseModel):
    """Raw structured output from the checklist LLM call (concern mode)."""

    probe_hypotheses: list[ConcernHypothesis] = Field(
        description="Per-node probing hypotheses across the concern axes, each with a reason."
    )


class _WellnessChecklistLLMOutput(BaseModel):
    """Raw structured output from the checklist LLM call (wellness mode)."""

    probe_hypotheses: list[WellnessHypothesis] = Field(
        description="Proactive probing hypotheses across the wellness axes, each with a reason."
    )


class PreconsultationSummaries(BaseModel):
    """The doctor-facing output: two markdown summaries + a scored probe checklist."""

    preconsultation_summary: str
    family_risk_summary: str
    preconsultation_checklist: list[ChecklistProbe]


def _score_hypotheses(hypotheses: list[_HypothesisBase]) -> list[ChecklistProbe]:
    """Turn raw hypotheses into scored checklist probes.

    Base score = probability * tag_weight, where tag_weight (_TAG_WEIGHT) is a
    moderate per-axis importance multiplier so clinically urgent axes (e.g.
    contradiction_resolution) float up. It is INTERNAL — it shapes `score` only
    and is never exposed on ChecklistProbe.

    Then an INTRA-TAG RANK DECAY is applied: within each tag the probes are
    ranked by base score and discounted by `_TAG_RANK_DECAY ** rank`, so a tag
    that emits many strong probes can't monopolize the top of the list and bury
    the single best probe of another tag. Final list is sorted by the adjusted
    score, descending.
    """
    logger.debug(
        "[score] scoring %d hypotheses (tag_rank_decay=%s)",
        len(hypotheses),
        _TAG_RANK_DECAY,
    )

    # First pass: base score per hypothesis.
    scored: list[tuple[_HypothesisBase, float]] = []
    for h in hypotheses:
        tag_weight = _TAG_WEIGHT.get(h.tag, _DEFAULT_TAG_WEIGHT)
        base = h.probability * tag_weight
        scored.append((h, base))
        logger.debug(
            "[score]   tag=%r prob=%.3f x tag_weight=%.2f -> base=%.3f",
            h.tag,
            h.probability,
            tag_weight,
            base,
        )

    # Group by tag and apply the rank decay within each tag.
    by_tag: dict[str, list[tuple[_HypothesisBase, float]]] = {}
    for h, base in scored:
        by_tag.setdefault(h.tag, []).append((h, base))

    items: list[ChecklistProbe] = []
    for tag, group in by_tag.items():
        group.sort(key=lambda hb: hb[1], reverse=True)
        logger.debug(
            "[score] tag=%r has %d hypotheses -> applying intra-tag rank decay",
            tag,
            len(group),
        )
        for rank, (h, base) in enumerate(group):
            decay = _TAG_RANK_DECAY**rank
            adjusted = base * decay
            logger.debug(
                "[score]   rank=%d base=%.3f x decay=%.3f -> adjusted=%.3f%s",
                rank,
                base,
                decay,
                adjusted,
                "  <-- suppressed by rank" if rank > 0 else "",
            )
            items.append(
                ChecklistProbe(
                    probe=h.probe,
                    tag=h.tag,
                    score=round(adjusted, 3),
                    reason=h.reason,
                )
            )
    items.sort(key=lambda i: i.score, reverse=True)
    logger.debug("[score] final checklist order (after cross-tag re-sort):")
    for i, item in enumerate(items):
        logger.debug(
            "[score]   #%d  score=%.3f  tag=%r  probe=%r",
            i + 1,
            item.score,
            item.tag,
            item.probe,
        )
    return items


async def areorder_onboarding_summary(
    summary_text: str,
    client_details: dict,
    llm,
    callbacks: list | None = None,
    output_style: str = "paragraph",
) -> str:
    """Second pass over the onboarding summary: re-sequence the already-written
    output so the most critical findings lead, preserving every fact and the
    register/format (`output_style`) of the first output.

    The priority order is computed deterministically from salience
    (`summary_priority`); the LLM only re-sequences the prose to match it. Empty
    or trivial input is returned unchanged (nothing to reorder)."""
    if not (summary_text or "").strip():
        return summary_text
    priority_order = summary_priority(client_details)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.build_reorder_summary_system_prompt(output_style)),
            ("human", prompts.REORDER_SUMMARY_HUMAN_PROMPT),
        ]
    )
    chain = prompt | llm.with_structured_output(_ReorderedSummary)
    out = await _run_llm(
        "reorder_summary",
        _client_id(client_details),
        chain.ainvoke(
            {"summary": summary_text, "priority_order": priority_order},
            config=_run_config(callbacks),
        ),
    )
    reordered = (out.summary or "").strip()
    logger.debug(
        "\n################## ONBOARDING SUMMARY REORDER ##################\n"
        "[priority order]\n%s\n\n[before]\n%s\n\n[after]\n%s\n"
        "################## END REORDER ##################",
        priority_order,
        summary_text,
        reordered,
    )
    return reordered or summary_text


async def areorder_family_risk_summary(
    family_text: str,
    client_details: dict,
    llm,
    callbacks: list | None = None,
    output_style: str = "paragraph",
) -> str:
    """Second pass over the family-risk summary: re-sequence it so hereditary
    conditions DIRECTLY RELATED to the patient's own current health patterns
    appear earliest, then the rest by descending risk — preserving every fact,
    the no-verdict framing, the no-"patient" rule, and the format
    (`output_style`) of the first output.

    The priority order (directly-related-first) is computed deterministically
    from salience (`family_risk_priority`, driven by the authoritative family
    cross-references); the LLM only re-sequences the prose. Empty input is
    returned unchanged."""
    if not (family_text or "").strip():
        return family_text
    priority_order = family_risk_priority(client_details)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.build_reorder_family_risk_system_prompt(output_style)),
            ("human", prompts.REORDER_FAMILY_RISK_HUMAN_PROMPT),
        ]
    )
    chain = prompt | llm.with_structured_output(_ReorderedSummary)
    out = await _run_llm(
        "reorder_family",
        _client_id(client_details),
        chain.ainvoke(
            {"summary": family_text, "priority_order": priority_order},
            config=_run_config(callbacks),
        ),
    )
    reordered = (out.summary or "").strip()
    logger.debug(
        "\n################## FAMILY-RISK REORDER ##################\n"
        "[priority order]\n%s\n\n[before]\n%s\n\n[after]\n%s\n"
        "################## END REORDER ##################",
        priority_order,
        family_text,
        reordered,
    )
    return reordered or family_text


def _post_webhook(payload: dict) -> None:
    """Blocking POST to the preconsultation tool webhook; response is logged."""
    try:
        body = json.dumps(payload, separators=(",", ":")).encode()
        secret = os.environ.get("ONBOARDING_WEBHOOK_SECRET", "")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Onboarding-Signature": f"sha256={signature}",
        }
        resp = requests.post(
            WEBHOOK_URL, data=body, headers=headers, timeout=10
        )
        logger.info(
            "Webhook posted to %s: status=%s, response=%s",
            WEBHOOK_URL,
            resp.status_code,
            resp.text,
        )
    except Exception as exc:
        logger.warning("Webhook post to %s failed: %s", WEBHOOK_URL, exc)


def _fire_webhook(payload: dict) -> None:
    """Fire-and-forget the webhook on a background daemon thread.

    Returns immediately; the POST runs off-thread and is never awaited or
    validated. Safe to call from both sync and async code paths.
    """
    threading.Thread(target=_post_webhook, args=(payload,), daemon=True).start()


def _patient_baseline(client_details: dict) -> dict:
    return client_details.get("patient_baseline", {})


def _client_id(client_details: dict) -> str:
    """Trace/correlation id for a run — the form's patient_baseline.id."""
    return _patient_baseline(client_details).get("id", "")


def _patient_age(client_details: dict) -> int | str:
    """Age in whole years from patient_baseline.date_of_birth, or '?' if absent."""
    dob = _patient_baseline(client_details).get("date_of_birth")
    if not dob:
        return "?"
    born = date.fromisoformat(dob)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _patient_name(client_details: dict) -> str:
    baseline = _patient_baseline(client_details)
    return " ".join(
        p for p in (baseline.get("first_name"), baseline.get("last_name")) if p
    ).strip()


def _patient_email(client_details: dict) -> str:
    return _patient_baseline(client_details).get("contact_email", "")


def _mock_summaries(client_details: dict) -> PreconsultationSummaries:
    """Return a fixed dummy result whose shape mirrors a real response.

    IDs and names are derived from client_details so callers can still
    correlate the result to the input without making any LLM calls.
    """
    name = _patient_name(client_details) or "unknown"
    age = _patient_age(client_details)
    gender = _patient_baseline(client_details).get("gender", "?")
    clusters = sorted(
        client_details.get("cluster_scores", []),
        key=lambda c: c.get("final_score", 0),
        reverse=True,
    )
    cluster_hint = clusters[0]["cluster_label"] if clusters else "General Health"

    return PreconsultationSummaries(
        preconsultation_summary=(
            f"[MOCK] Patient {name} — {age}yo {gender}. "
            f"Primary pattern: {cluster_hint}. This is a mock summary; "
            "no LLM was called."
        ),
        family_risk_summary=(
            "[MOCK] No family risk analysis performed. "
            "This is a mock result; no LLM was called."
        ),
        preconsultation_checklist=[
            ChecklistProbe(
                probe="[MOCK] Confirm primary cluster findings",
                tag="diagnostic_clarification",
                score=0.5,
                reason="[MOCK] Placeholder probe; no LLM was called.",
            )
        ],
    )


_SUMMARIZE_DOC = """Summarize one patient form into the three sections.

    Args:
        client_details: one v3 pre-consultation form export. Must include a
            "patient_baseline" with a non-empty "id" and the required form keys
            (concerns, medical_history, cluster_scores, health_goals,
            lifestyle_answers); a ValueError is raised otherwise.
        llm: any LangChain chat model. Overrides model/config entirely when set.
        model: model name override (e.g. "gpt-4o"). Takes precedence over
               llm_config but not over an explicit `llm` instance.
        trigger_webhook: POST the result to the preconsultation tool endpoint
                         after generation. Fires on a background thread;
                         response is not awaited or validated.
        mock: when True, skip all LLM calls and return a fixed dummy result
              whose structure mirrors a real response. The webhook is also
              skipped. Useful for integration testing without API keys.
        output_style: format of the two summaries — "paragraph" (dense prose,
              the default) or "markdown" (grouped bullet points).
        output_size: how much detail the two summaries carry —
              "small"  (only the most critical findings),
              "medium" (balanced; the default/historical behaviour),
              "large"  (exhaustive; every recorded finding), or
              "all"    (render small+medium+large).

    Returns a JSON-serialisable dict (each carrying its own "output_style" and
    "output_size"). When output_size="all", returns a LIST of such dicts, one
    per concrete size; the probe checklist is identical across them.
    """


def _run_sync(coro):
    """Run a coroutine to completion from sync code, tolerating a running loop
    (mirrors the guard in extract_insights)."""
    try:
        asyncio.get_running_loop()
        import nest_asyncio

        nest_asyncio.apply()
    except RuntimeError:
        pass
    return asyncio.run(coro)


# The concrete sizes rendered when output_size == "all".
_ALL_SIZES = ("small", "medium", "large")


def _validate_output_opts(output_style: str, output_size: str) -> None:
    """Reject unknown style/size knobs up front (mirrors validate_summary_input)."""
    if output_style not in prompts.OUTPUT_STYLES:
        raise ValueError(
            f"output_style must be one of {prompts.OUTPUT_STYLES}, got {output_style!r}"
        )
    if output_size not in prompts.OUTPUT_SIZES:
        raise ValueError(
            f"output_size must be one of {prompts.OUTPUT_SIZES}, got {output_size!r}"
        )


async def _generate_summaries(
    output_style: str,
    output_size: str,
    profile: str,
    client_details: dict,
    summary_llm,
    callbacks: list,
) -> tuple[str, str]:
    """LLM call 1 (the two prose summaries) plus both reorder passes, for one
    concrete style/size combination. Returns
    (preconsultation_summary, family_risk_summary).

    The checklist is size-independent and is generated once by the caller, so it
    is not produced here.

    Empty-input guards (nothing to summarize -> empty string): if the salience
    profile is blank, no LLM call is made and both summaries are "". If the
    patient has no nested family history at all, the family-risk summary is forced
    to "" (and its reorder skipped) regardless of what the LLM emitted."""
    if not (profile or "").strip():
        logger.debug("[summaries] empty profile -> returning empty summaries")
        return "", ""
    want_family = has_family_history(client_details)
    summary_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompts.build_summary_system_prompt(output_style, output_size)),
            ("human", prompts.HUMAN_PROMPT),
        ]
    )
    summary_inputs = {"profile": profile}
    summary_chain = summary_prompt | summary_llm.with_structured_output(
        _SummaryLLMOutput
    )
    summaries_raw = await _run_llm(
        f"summaries[{output_size}]",
        _client_id(client_details),
        summary_chain.ainvoke(summary_inputs, config=_run_config(callbacks)),
    )
    logger.debug(
        "\n"
        "################## LLM CALL 1 (summaries, style=%s size=%s) — OUTPUT ##################\n"
        "[preconsultation_summary]\n%s\n\n"
        "[family_risk_summary]\n%s\n"
        "################## END CALL 1 OUTPUT ##################",
        output_style,
        output_size,
        summaries_raw.preconsultation_summary,
        summaries_raw.family_risk_summary,
    )
    # No family history in the data -> nothing to summarize; force empty and skip
    # its reorder (guards against the LLM hallucinating a family-risk paragraph).
    family_text = summaries_raw.family_risk_summary if want_family else ""
    # Reorder both by deterministic priority, preserving the chosen output_style.
    return await asyncio.gather(
        areorder_onboarding_summary(
            summaries_raw.preconsultation_summary,
            client_details,
            summary_llm,
            callbacks,
            output_style,
        ),
        areorder_family_risk_summary(
            family_text,
            client_details,
            summary_llm,
            callbacks,
            output_style,
        ),
    )


def _assemble_variant(
    output_style: str,
    size_tag: str,
    summaries: tuple[str, str],
    checklist_items: list[ChecklistProbe],
) -> dict:
    """Bundle one size variant's two summaries with the shared checklist."""
    pre_summary, fam_summary = summaries
    result = PreconsultationSummaries(
        preconsultation_summary=pre_summary,
        family_risk_summary=fam_summary,
        preconsultation_checklist=checklist_items,
    )
    return {
        "output_style": output_style,
        "output_size": size_tag,
        **json.loads(result.model_dump_json()),
    }


async def _run_patient_pipeline(
    client_details: dict,
    llm,
    model: str | None,
    profile: str,
    seeds: str,
    output_style: str,
    output_size: str,
    handler,
    span,
):
    """The LLM work for one client: the size-independent checklist call plus one
    or more summary variants (small/medium/large), all nested under `span`.

    Runs inside the parent Langfuse span so every call is a child of one trace.
    Records the checklist summary on the trace via `span.update_trace(...)` before
    returning. Returns one dict, or a list of dicts when output_size == "all"."""
    callbacks = [handler] if handler else []

    # --- Call 1 (summaries) LLM: reused across every size variant.
    summary_llm = llm or build_llm("summarize_patient", model)
    if llm is not None:
        logger.debug(
            "[llm] call 1 uses caller-supplied llm instance (config ignored)"
        )
    # Extract demographics for LLM prompts (age/gender used for contradiction detection)
    age = _patient_age(client_details)
    gender = _patient_baseline(client_details).get("gender", "?")

    # --- Call 2 setup: probe checklist with reasons. Mode picks the axes and
    # the output schema. The checklist is INDEPENDENT of output_style/
    # output_size, so it is built once and (for output_size="all") shared
    # across every size variant.
    mode = patient_mode(client_details)
    if mode == WELLNESS:
        checklist_system = prompts.WELLNESS_CHECKLIST_SYSTEM_PROMPT
        checklist_output = _WellnessChecklistLLMOutput
    else:
        checklist_system = prompts.CHECKLIST_SYSTEM_PROMPT
        checklist_output = _ConcernChecklistLLMOutput
    logger.debug(
        "[flow] checklist mode=%r (no strong cluster => wellness) -> prompt=%s, output=%s",
        mode,
        (
            "WELLNESS_CHECKLIST_SYSTEM_PROMPT"
            if mode == WELLNESS
            else "CHECKLIST_SYSTEM_PROMPT"
        ),
        checklist_output.__name__,
    )

    checklist_llm = build_llm("generate_checklist", model)
    checklist_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", checklist_system),
            ("human", prompts.CHECKLIST_HUMAN_PROMPT),
        ]
    )
    checklist_inputs = {"profile": profile, "seeds": seeds, "age": age, "gender": gender}
    checklist_chain = checklist_prompt | checklist_llm.with_structured_output(
        checklist_output
    )

    # output_size="all" -> render every concrete size; otherwise just the one.
    # The single checklist call runs concurrently with all summary variants.
    sizes = list(_ALL_SIZES) if output_size == "all" else [output_size]
    logger.debug(
        "[flow] generating summaries for style=%r size(s)=%s", output_style, sizes
    )
    checklist_raw, *summaries_variants = await asyncio.gather(
        _run_llm(
            "checklist",
            _client_id(client_details),
            checklist_chain.ainvoke(checklist_inputs, config=_run_config(callbacks)),
        ),
        *(
            _generate_summaries(
                output_style, sz, profile, client_details, summary_llm, callbacks
            )
            for sz in sizes
        ),
    )

    output_lines = "\n".join(
        f"  - tag={h.tag!r} prob={h.probability:.3f}\n"
        f"      probe : {h.probe}\n"
        f"      reason: {h.reason}"
        for h in checklist_raw.probe_hypotheses
    )
    logger.debug(
        "\n"
        "################## LLM CALL 2 (checklist) — OUTPUT (%d raw hypotheses, pre-scoring) ##################\n"
        "%s\n"
        "################## END CALL 2 OUTPUT ##################",
        len(checklist_raw.probe_hypotheses),
        output_lines,
    )

    # Score the (shared) checklist once; every size variant carries the same one.
    checklist_items = _score_hypotheses(checklist_raw.probe_hypotheses)

    results = [
        _assemble_variant(output_style, sz, variant, checklist_items)
        for sz, variant in zip(sizes, summaries_variants)
    ]
    logger.debug(
        "[flow] asummarize_patient done: %d summary variant(s), %d checklist items",
        len(results),
        len(checklist_items),
    )

    if span is not None:
        try:
            span.update_trace(
                output={
                    "checklist_count": len(checklist_items),
                    "checklist": [
                        {"probe": p.probe, "tag": p.tag, "score": p.score}
                        for p in checklist_items
                    ],
                }
            )
        except Exception as exc:
            logger.warning("[langfuse] trace finalize failed: %s", exc)

    # Backwards-compatible: a single size returns one dict; "all" returns a list.
    return results if output_size == "all" else results[0]


async def asummarize_patient(
    client_details: dict,
    llm=None,
    model: str | None = None,
    trigger_webhook: bool = True,
    mock: bool = False,
    debug: bool = False,
    output_style: str = "paragraph",
    output_size: str = "medium",
) -> PreconsultationSummaries:
    validate_summary_input(client_details)
    _validate_output_opts(output_style, output_size)
    if debug:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.DEBUG)
    else:
        logging.getLogger("intelligence_engine.preconsultation").setLevel(logging.WARNING)
    logger.debug(
        "[flow] asummarize_patient start: client_id=%s mock=%s trigger_webhook=%s "
        "model_override=%s output_style=%s output_size=%s",
        _client_id(client_details),
        mock,
        trigger_webhook,
        model,
        output_style,
        output_size,
    )

    if mock:
        logger.debug(
            "[flow] mock=True -> returning fixed dummy result, NO LLM calls"
        )
        mock_dict = json.loads(_mock_summaries(client_details).model_dump_json())
        if output_size == "all":
            return [
                {"output_style": output_style, "output_size": sz, **mock_dict}
                for sz in _ALL_SIZES
            ]
        return {
            "output_style": output_style,
            "output_size": output_size,
            **mock_dict,
        }

    if trigger_webhook:
        payload = {
            **client_details,
            "email": _patient_email(client_details),
            "name": _patient_name(client_details),
        }
        logger.debug(
            "[flow] firing webhook (fire-and-forget) to %s for client_id=%s",
            WEBHOOK_URL,
            _client_id(client_details),
        )
        _fire_webhook(payload)
    else:
        logger.debug("[flow] trigger_webhook=False -> webhook skipped")

    client_id = _client_id(client_details)
    with log_stage("summarize_patient total", client_id=client_id):
        # --- Deterministic preprocessing (no LLM): this is the exact signal the
        # model will see. Inspect it to judge whether salience captured the right
        # findings before any LLM cost is paid. Both LLM calls share one rich,
        # identity-free profile (reported concerns + medical history + clusters).
        # A malformed nested shape validation didn't catch surfaces here as a
        # typed SummaryGenerationError, not a raw KeyError.
        try:
            with log_stage("preprocess", client_id=client_id):
                profile = build_full_profile(client_details)
                seeds = prompts.render_seeds(checklist_seeds(client_details))
        except SummaryGenerationError:
            raise
        except Exception as exc:
            raise SummaryGenerationError(
                f"preprocessing failed: {exc}",
                stage="preprocess",
                client_id=client_id,
                cause=exc,
            ) from exc

        logger.debug(
            "[preprocess] checklist seeds (deterministic gaps):\n%s", seeds
        )
        # NOTE: the full prioritized profile text is shown inline in the rendered
        # LLM CALL 1/2 input prompts below, so it is not dumped separately here.

        # One parent Langfuse span per client: both LLM calls and every reorder
        # pass nest under it as a single expandable trace (patient_trace_span).
        # Flush after the span closes so the whole tree is exported together.
        langfuse_client = build_client(LANGFUSE_ENVIRONMENT)
        with patient_trace_span(
            langfuse_client, client_id, LANGFUSE_ENVIRONMENT
        ) as (handler, span):
            result = await _run_patient_pipeline(
                client_details,
                llm,
                model,
                profile,
                seeds,
                output_style,
                output_size,
                handler,
                span,
            )
        if langfuse_client is not None:
            try:
                langfuse_client.flush()
            except Exception:
                pass
    return result


def summarize_patient(
    client_details: dict,
    llm=None,
    model: str | None = None,
    trigger_webhook: bool = True,
    mock: bool = False,
    debug: bool = False,
    output_style: str = "paragraph",
    output_size: str = "medium",
) -> PreconsultationSummaries:
    return _run_sync(
        asummarize_patient(
            client_details,
            llm=llm,
            model=model,
            trigger_webhook=trigger_webhook,
            mock=mock,
            debug=debug,
            output_style=output_style,
            output_size=output_size,
        )
    )


asummarize_patient.__doc__ = _SUMMARIZE_DOC
summarize_patient.__doc__ = (
    "Synchronous wrapper around asummarize_patient.\n\n" + _SUMMARIZE_DOC
)
