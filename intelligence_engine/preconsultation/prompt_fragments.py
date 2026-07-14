"""Reusable prompt instruction fragments for demographic awareness.

These fragments are composed into the main prompts to keep instructions DRY and
maintainable. The intent is RESTRAINT: most patients have no demographic anomaly
at all, so the model should only react when a finding is genuinely incompatible
with — or strikingly atypical for — the patient's age and gender. There is no
dedicated "anomaly tag" and no scripted score adjustment; a real anomaly is just
classified under whichever existing tag fits it best and scored on its own merits.
"""

# ---------------------------------------------------------------------------
# Age & Gender Awareness (restrained)
# ---------------------------------------------------------------------------

AGE_GENDER_AWARENESS = """\
DEMOGRAPHIC AWARENESS (use sparingly):
Keep the patient's age and gender in mind as background context. The DEFAULT
assumption is that findings are consistent with the demographics — most patients
have NO demographic anomaly, so do not go looking for one. Only react when a
finding is clearly incompatible with the age/gender (e.g., a male patient with a
pregnancy finding) or so far outside the typical age of onset that it reads as a
likely data error (e.g., advanced Parkinson's in a 30-year-old).

When — and only when — such a genuine mismatch exists:
- Do NOT invent a special tag for it. Classify it under whichever existing tag
  fits the clinical situation most naturally (often diagnostic_clarification or
  red_flag_escalation; use contradiction_resolution ONLY if the finding truly
  conflicts with another data point, not merely because it is unusual).
- Let its score reflect genuine clinical concern, not the mere fact that it is
  age-atypical. A mildly early/late finding is not an anomaly and needs no
  special handling.

Do not treat "needs validation", "low confidence", or "worth confirming" as
demographic anomalies — those are ordinary clinical uncertainty, handled by the
normal tags, not by demographic reasoning.
"""

# ---------------------------------------------------------------------------
# Consolidated Demographics Instructions
# ---------------------------------------------------------------------------

def build_demographics_instruction(context: str) -> str:
    """Build the demographic-awareness instruction for a given context.

    Args:
        context: one of "summary", "checklist", or "insight".

    Returns:
        The awareness block, lightly tailored to the context. Intentionally
        restrained — no scripted tag routing or score deltas.
    """
    if context == "checklist":
        return AGE_GENDER_AWARENESS
    elif context == "insight":
        return (
            AGE_GENDER_AWARENESS
            + "\nFor necessity scoring: a finding that is genuinely incompatible "
            "with the patient's age/gender is likely a data error, so rank it "
            "LOWER (the doctor should verify it before acting). Apply this only "
            "to clear mismatches — do not penalize findings merely for being "
            "uncommon."
        )
    else:  # "summary"
        return (
            AGE_GENDER_AWARENESS
            + "\nFor the summary: do not mention demographic anomalies in the "
            "prose even if you notice one — the prose stays purely descriptive."
        )
