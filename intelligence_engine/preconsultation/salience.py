"""Deterministic, criticality-first preprocessing of a v3 pre-consultation form.

The job here is to do everything we can *without* an LLM:
  - rank each cluster by its upstream criticality (`final_score` / `bucket_id`),
  - render a compact, identity-free profile so the LLM sees signal, not noise,
  - surface objective gaps as checklist seeds.

This keeps token cost bounded regardless of how large a form grows, and keeps
the summaries focused on what actually matters for the consultation.

Input is the raw `directive_schema_id 3.0.1` export. Key facts about the shape:
  - The CLUSTER (`cluster_scores[]`) is the unit of criticality; there are no
    "nodes". `final_score` (0-100) and `bucket_id` carry criticality directly.
  - The rich descriptive findings are the patient's `concerns[]`.
  - `family_history` is nested INSIDE each concern, so every hereditary signal is
    intrinsically tied to the patient's own reported condition.
  - Labels (`*_label`) are the human-readable values; ids are internal join keys.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# --- Criticality ---------------------------------------------------------
# The upstream engine already scored each cluster. `final_score` (0-100) is the
# authoritative criticality; `bucket_id` is its categorical band.
_BUCKET_BAND: dict[str, str] = {
    "very_strong_pattern": "HIGH",
    "strong_pattern": "MODERATE",
    "weak_signal": "LOW",
}
_DEFAULT_BAND = "MODERATE"

HIGH, MODERATE, LOW = "HIGH", "MODERATE", "LOW"

# Buckets that make a patient "concern" (pressing findings) rather than
# "wellness" (broadly healthy → proactive, preventive checklist).
_CONCERN_BUCKETS = {"strong_pattern", "very_strong_pattern"}
CONCERN, WELLNESS = "concern", "wellness"

# A concern we are this unsure about is treated as ambiguous (checklist seed).
LOW_CONFIDENCE = 70

# Tokens that mean "absent / negative" — used only to drop structurally-vacuous
# entries. A clinically meaningful "no" is NOT dropped here; it is rendered as a
# pertinent-negative note and the prompt decides whether it matters.
_NEGATIVE_TOKENS = {"no", "none", "nil", ""}

# Ordering weights for concerns (internal only — never surfaced). Ids are fine
# for ordering; labels are what we render.
_FUNCTIONAL_RANK = {"regularly": 3, "occasionally": 2, "minimal": 1}
_PROGRESSION_BONUS = {
    "rapidly_worsening": 2,
    "gradually_worsening": 1,
    "stable": 0,
    "improving": -1,
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _is_negative(value: str | None) -> bool:
    return (value or "").strip().lower() in _NEGATIVE_TOKENS


def score_cluster(cluster: dict) -> float:
    """Cluster criticality in [0, 1], straight from the upstream `final_score`."""
    return round(_clamp(cluster.get("final_score", 0) / 100.0), 3)


def cluster_band(cluster: dict) -> str:
    """Categorical criticality band for a cluster, from its `bucket_id`."""
    return _BUCKET_BAND.get(cluster.get("bucket_id"), _DEFAULT_BAND)


def cluster_score_map(patient: dict) -> dict[str, float]:
    """Map each `cluster_label` to its criticality score. Used downstream to
    weight probe hypotheses by the criticality of the cluster they touch."""
    return {
        c["cluster_label"]: score_cluster(c) for c in patient["cluster_scores"]
    }


def patient_mode(patient: dict) -> str:
    """CONCERN if any cluster is a (very) strong pattern, else WELLNESS.

    Drives which checklist prompt + scoring path is used downstream: pressing
    patients get the diagnostic axes, healthy patients get the proactive ones.
    """
    buckets = {c.get("bucket_id") for c in patient["cluster_scores"]}
    pressing = buckets & _CONCERN_BUCKETS
    if pressing:
        logger.debug("[mode] CONCERN: pressing buckets present: %s", pressing)
        return CONCERN
    logger.debug("[mode] WELLNESS: no strong/very-strong cluster")
    return WELLNESS


# --- Concern helpers -----------------------------------------------------

def _concern_severity(concern: dict) -> float:
    """Internal ordering weight for a concern (higher = more pressing)."""
    functional = _FUNCTIONAL_RANK.get(concern.get("functional_impact_id"), 0)
    progression = _PROGRESSION_BONUS.get(concern.get("progression_impact_id"), 0)
    confidence = concern.get("confidence_score", 0) / 100.0
    return functional * 10 + progression * 5 + confidence


def _sorted_concerns(patient: dict) -> list[dict]:
    return sorted(patient["concerns"], key=_concern_severity, reverse=True)


def _family_history_str(fh: dict) -> str:
    """Format one nested family-history entry: 'Mother (50–60)'."""
    who = fh.get("relation_label", "relative")
    band = fh.get("age_band_label")
    return f"{who} ({band})" if band else who


# --- Prioritized profile (LLM input) -------------------------------------

def build_full_profile(patient: dict) -> str:
    """Rich, identity-free profile used for BOTH LLM calls (summaries + checklist).

    Contains NO personal/identifying details (no name, age, gender, id). Renders
    the patient's reported concerns as the primary findings — each with its
    impact, duration, trend, symptoms, how they know it, its nested (patient-
    linked) family history, and its validation answers — then medical history,
    lifestyle factors, and the scored health patterns (clusters). Structurally-
    vacuous negatives are dropped; pertinent negatives are kept compactly.
    """
    lines: list[str] = []

    goals = _sorted_goal_labels(patient)
    if goals:
        lines.append("Stated goals (in priority order): " + ", ".join(goals))

    concerns = _sorted_concerns(patient)
    if concerns:
        lines.append("")
        lines.append("Reported concerns (patient-declared), most pressing first:")
        for concern in concerns:
            lines.extend(_render_concern(concern))

    lines.extend(_render_medical_history(patient.get("medical_history", {})))

    lifestyle = _render_lifestyle(patient.get("lifestyle_answers", []))
    if lifestyle:
        lines.append("")
        lines.append("Lifestyle factors: " + "; ".join(lifestyle))

    lines.extend(_render_clusters(patient))

    return "\n".join(lines)


def _sorted_goal_labels(patient: dict) -> list[str]:
    goals = sorted(
        patient.get("health_goals", []), key=lambda g: g.get("priority", 99)
    )
    return [g["goal_label"] for g in goals]


def _render_concern(concern: dict) -> list[str]:
    """Render one concern: the finding line plus its evidence, symptoms, sources,
    patient-linked family history, and validation answers."""
    out: list[str] = [
        f"- {concern['concern_label']} — affects daily life: "
        f"{concern.get('functional_impact_label', '?')}; "
        f"duration: {concern.get('duration_impact_label', '?')}; "
        f"trend: {concern.get('progression_impact_label', '?')}"
    ]

    sources = [s["source_label"] for s in concern.get("concern_sources", [])]
    if sources:
        out.append(f"        known via: {', '.join(sources)}")

    symptoms = [s["symptom_label"] for s in concern.get("symptoms", [])]
    if symptoms:
        out.append(f"        symptoms: {', '.join(symptoms)}")

    family = concern.get("family_history", [])
    if family:
        rendered = ", ".join(_family_history_str(fh) for fh in family)
        out.append(
            f"        family history for this condition (hereditary signal): {rendered}"
        )

    answers = concern.get("cluster_probe_answers", [])
    positives = [a["probe_label"] for a in answers if a.get("value") == "yes"]
    negatives = [a["probe_label"] for a in answers if a.get("value") == "no"]
    if positives:
        out.append(f"        reported yes to: {'; '.join(positives)}")
    if negatives:
        out.append(f"        answered no to: {'; '.join(negatives)}")

    return out


def _render_medical_history(mh: dict) -> list[str]:
    """Render diagnoses (≠ None), medications, allergies, surgeries. Empty and
    'None'/'no' entries are dropped."""
    out: list[str] = []

    diagnoses = [
        d["diagnosis_label"]
        for d in mh.get("diagnoses", [])
        if not _is_negative(d.get("diagnosis_label"))
    ]
    if diagnoses:
        out.append("Existing diagnoses: " + ", ".join(diagnoses))

    medications = [_medication_str(m) for m in mh.get("medications", [])]
    if medications:
        out.append("Current medications: " + ", ".join(medications))

    allergies = [a["name"] for a in mh.get("allergies", []) if a.get("name")]
    if allergies:
        out.append("Allergies: " + ", ".join(allergies))

    surgeries = [_surgery_str(s) for s in mh.get("surgeries", []) if s]
    if surgeries:
        out.append("Surgical history: " + ", ".join(surgeries))

    reproductive = _render_sexual_health(mh.get("sexual_health_answers", []))
    if reproductive:
        out.append("Reproductive / sexual health: " + "; ".join(reproductive))

    return out


def _medication_str(med: dict) -> str:
    parts = [med.get("name", "?")]
    detail = [
        med[k] for k in ("dosage", "frequency", "duration") if med.get(k)
    ]
    if detail:
        parts.append(f"({', '.join(detail)})")
    return " ".join(parts)


def _surgery_str(surgery: dict) -> str:
    """Render one medical_history.surgeries entry: name (area, when, reason)."""
    name = surgery.get("name")
    if not name:
        return ""
    extras = [
        str(surgery[k])
        for k in ("area", "performed_when", "reason")
        if surgery.get(k) not in (None, "")
    ]
    return f"{name} ({', '.join(extras)})" if extras else str(name)


def _render_sexual_health(answers: list[dict]) -> list[str]:
    """Positive findings inline; meaningful negatives kept as a compact note so
    the prompt can judge pertinent negatives (e.g. 'trying to conceive? no')."""
    positives = [
        f"{a['question_label']}: {a['option_label']}"
        for a in answers
        if not _is_negative(a.get("option_id"))
    ]
    negatives = [
        a["question_label"] for a in answers if _is_negative(a.get("option_id"))
    ]
    out = list(positives)
    if negatives:
        out.append(f"answered no to: {', '.join(negatives)}")
    return out


def _render_lifestyle(answers: list[dict]) -> list[str]:
    """Present lifestyle values (drops pure-absence answers like tobacco: none)."""
    return [
        f"{a['field_label']}: {a['option_label']}"
        for a in answers
        if not _is_negative(a.get("option_value"))
    ]


def _render_clusters(patient: dict) -> list[str]:
    """Health patterns (clusters), strongest first. Weak-signal clusters are
    collapsed to a single context line so they inform without diluting focus."""
    scored = sorted(
        patient["cluster_scores"], key=score_cluster, reverse=True
    )
    strong = [c for c in scored if cluster_band(c) != LOW]
    weak = [c for c in scored if cluster_band(c) == LOW]

    out: list[str] = []
    if not strong and not weak:
        return out

    out.append("")
    out.append("Health patterns (clusters), strongest first:")
    for cluster in strong:
        out.append(f"- {cluster['cluster_label']} [{cluster.get('bucket_label', '?')}]")
        drivers = [
            s["signal_label"] for s in cluster.get("lifestyle_signals_triggered", [])
        ]
        if drivers:
            out.append(f"        lifestyle drivers: {', '.join(drivers)}")
        if cluster.get("family_risk_contribution", 0) > 0:
            out.append(
                f"        family history contributes to this pattern"
            )
    if weak:
        labels = ", ".join(c["cluster_label"] for c in weak)
        out.append(f"- Lower-signal patterns (context only): {labels}")
    return out


# --- Checklist seeds (objective gaps the LLM should phrase/prioritize) ----

def checklist_seeds(patient: dict) -> list[str]:
    """Deterministically detected gaps and ambiguities. These seed the checklist;
    the LLM phrases them clinically, prioritizes, and may add follow-ups it
    infers. Pure-LLM checklists drift generic — concrete seeds keep it specific."""
    seeds: list[str] = []

    for concern in patient["concerns"]:
        label = concern["concern_label"]
        confidence = concern.get("confidence_score", 100)
        if confidence < LOW_CONFIDENCE:
            seeds.append(
                f"Low confidence ({confidence}) on reported concern '{label}' — "
                f"confirm or rule out."
            )
            logger.debug("[seed] concern %r confidence=%s (low)", label, confidence)
        if concern.get("probe_flagged") and concern.get("probe_question_count", 0) == 0:
            seeds.append(
                f"'{label}' was flagged for probing but no probe answers were "
                f"captured — clarify directly."
            )
            logger.debug("[seed] concern %r flagged but unprobed", label)

    mh = patient.get("medical_history", {})
    allergies = [a["name"] for a in mh.get("allergies", []) if a.get("name")]
    if allergies:
        seeds.append(
            f"Documented allergy to {', '.join(allergies)} — verify before "
            f"prescribing."
        )
        logger.debug("[seed] allergies: %s", allergies)

    for cluster in patient["cluster_scores"]:
        if (
            cluster_band(cluster) != LOW
            and cluster.get("validation_skip_reason") == "not_probed"
        ):
            seeds.append(
                f"'{cluster['cluster_label']}' pattern was not validated "
                f"(skipped: not_probed) — confirm it holds before acting on it."
            )
            logger.debug("[seed] cluster %r not_probed", cluster["cluster_label"])

    for answer in _notable_reproductive(mh):
        seeds.append(answer)

    logger.debug("[seed] %d checklist seed(s) detected", len(seeds))
    return seeds


def _notable_reproductive(mh: dict) -> list[str]:
    """Positive reproductive findings worth a probe (e.g. irregular periods)."""
    out: list[str] = []
    for a in mh.get("sexual_health_answers", []):
        if not _is_negative(a.get("option_id")):
            out.append(
                f"Reproductive finding: {a['question_label']} = {a['option_label']} "
                f"— consider its relevance."
            )
    return out


# --- Priority signals for the post-generation reorder pass ----------------
# The summaries are written in one LLM call, then reordered in a second pass so
# the most critical information leads. These helpers produce the canonical
# priority order (deterministic) that the reorder LLM re-sequences the prose to.


def summary_priority(patient: dict) -> str:
    """Health patterns in criticality order (strongest first) to anchor the
    onboarding-summary reorder pass. Each line carries its band so the reorder
    LLM knows what must lead and what is mere context."""
    scored = sorted(patient["cluster_scores"], key=score_cluster, reverse=True)
    lines: list[str] = []
    rank = 1
    for cluster in scored:
        lines.append(
            f"{rank}. [{cluster_band(cluster)}] {cluster['cluster_label']}"
        )
        rank += 1
    return "\n".join(lines) if lines else "(no findings)"


def family_risk_priority(patient: dict) -> str:
    """Hereditary conditions ranked for the family-risk reorder pass.

    Every family-history entry is nested under a reported concern, so all of them
    are DIRECTLY related to the patient's own conditions by construction. They are
    ordered by the parent concern's severity (most pressing first)."""
    lines: list[str] = []
    for concern in _sorted_concerns(patient):
        family = concern.get("family_history", [])
        if not family:
            continue
        who = ", ".join(_family_history_str(fh) for fh in family)
        lines.append(f"- {concern['concern_label']}: family history — {who}")

    if not lines:
        return "(no family history)"
    header = (
        "DIRECTLY RELATED to the patient's own conditions (all family history is "
        "tied to a reported concern; surface in this order):"
    )
    return "\n".join([header, *lines])
