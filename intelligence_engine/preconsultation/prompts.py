"""Prompts for the pre-consultation output.

Two LLM calls are made:
  1. Summaries call  — SYSTEM_PROMPT + HUMAN_PROMPT  → two prose paragraphs.
  2. Checklist call  — CHECKLIST_HUMAN_PROMPT plus one of two system prompts,
     chosen by patient mode (see salience.patient_mode):
       - CHECKLIST_SYSTEM_PROMPT          (concern: patient has pressing findings)
       - WELLNESS_CHECKLIST_SYSTEM_PROMPT (wellness: broadly healthy patient)
     Both → probe hypotheses with reasons.

Probe scoring/ordering is computed downstream, not by the model.

Prompt fragments are imported from prompt_fragments.py to keep instructions DRY
and maintainable — when anomaly detection rules change, update the fragment
and all prompts inherit the change.
"""

from decouple import config

from intelligence_engine.preconsultation import prompt_fragments

# ---------------------------------------------------------------------------
# Summaries call — composed from fragments so the two output knobs vary the
# prompt without duplicating the shared clinical instructions:
#   - output_style: "paragraph" (dense prose) | "markdown" (grouped bullets)
#   - output_size:  "small"  (only the most critical findings)
#                   "medium" (balanced — the historical default)
#                   "large"  (exhaustive — every recorded finding)
# Build the full system prompt with build_summary_system_prompt(style, size).
# ("all" is not a prompt variant — the orchestrator loops small/medium/large.)
# ---------------------------------------------------------------------------

OUTPUT_STYLES = ("paragraph", "markdown")
OUTPUT_SIZES = ("small", "medium", "large", "all")

_SUMMARY_PREAMBLE = """\
You are a clinical pre-consultation assistant. A doctor reads your output in \
the final minute before seeing the patient, so every line must earn its place: \
precise, scannable, and free of filler. Never invent findings, lab values, or \
diagnoses that are not in the provided data.

How to read the input (the labels tell you what each value means):
- REPORTED CONCERNS are the patient's own declared health concerns. Each carries \
how much it "affects daily life", its "duration", its "trend" (whether it is \
worsening, stable, or improving), the "symptoms" the patient reports, how the \
patient "knows" it (a lab/test result, family history, or symptoms), any \
"family history for this condition", and validation answers ("reported yes to" \
= things the patient confirmed; "answered no to" = things ruled out).
- HEALTH PATTERNS are the higher-level themes the concerns roll up into \
(e.g. Cardiometabolic Risk), listed strongest first, each with the lifestyle \
factors that drive it. The health patterns are the clinical headline; the \
reported concerns are the supporting detail.
- Health patterns are pre-ordered by criticality; lead with the strongest.
- A "family history for this condition" is a hereditary signal for THAT specific \
concern — i.e. the patient's own condition. Treat it as directly relevant to \
that concern, never as a free-floating risk.
- Treat an "answered no to" item as a finding ONLY when it is a clinically \
meaningful pertinent negative (it rules out a red flag or materially changes the \
picture); otherwise ignore it."""

# COVERAGE knob (output_size). Governs HOW MUCH of the data reaches both
# summaries — small keeps only the vital few, large is exhaustive.
_COVERAGE = {
    "small": """\
COVERAGE — SMALL (most important only): Be maximally selective. In the \
preconsultation summary include ONLY the few most critical findings — the \
strongest health pattern(s) and the single most pressing concern or two — plus \
only the non-finding context (diagnosis, medication) essential to them; \
deliberately omit everything moderate or minor. In the family-risk summary \
include ONLY the most significant hereditary conditions, those tied to the \
strongest current patterns. A doctor with fifteen seconds must get only what \
cannot be skipped.
HARD LIMIT: the preconsultation summary must be AT MOST 56 words. If it would \
run longer, DROP the least critical facts — never buy space by stripping grammar \
into fragments, and never exceed the cap.""",
    "medium": """\
COVERAGE — MEDIUM (balanced, default): Lead with the most critical findings and \
cover the clinically significant ones; mention weaker patterns only briefly, or \
omit them if they add no value. Include the pertinent diagnoses, medications, \
goals, and lifestyle context, and the clinically significant hereditary \
conditions.
HARD LIMIT: the preconsultation summary must be AT MOST 113 words. If it would \
run longer, DROP the least critical facts — never buy space by stripping grammar \
into fragments, and never exceed the cap.""",
    "large": """\
COVERAGE — LARGE (exhaustive): Leave nothing out. In the preconsultation summary \
include EVERY finding present in the data — every reported concern with its \
duration and trend, every diagnosis, medication, allergy, surgery, reproductive \
finding, and notable lifestyle factor — ordered most-critical-first. In the \
family-risk summary include EVERY hereditary condition from any concern's family \
history. Stay dense and non-repetitive, but omit nothing recorded.
HARD LIMIT: the preconsultation summary must be AT MOST 200 words. If it would \
run longer, DROP the least critical facts — never buy space by stripping grammar \
into fragments, and never exceed the cap.""",
}

# FORMAT knob (output_style) for section 1 (preconsultation summary).
_SUMMARY_FORMATS = {
    "paragraph": """\
1. PRECONSULTATION SUMMARY — write ONE continuous prose paragraph of plain, \
dense clinical statements. No headings, no markdown, no bullet points, no line \
breaks, no labels. Each sentence states facts directly and flows into the next.
   Target style:
   - Information-dense but GRAMMATICAL clinical prose — complete, well-formed \
sentences with real verbs, in the tone of a clinician's handover note. Dense \
means every word earns its place, NOT that words are missing.
   - NEVER chain facts into a semicolon-separated list. A run like "worsening \
hypertension >3 yrs with high readings; hypercholesterolemia and elevated HbA1c \
>3 yrs; central obesity; urinary symptoms" is a data dump, not a summary — it is \
the single worst failure mode here. Write those facts as sentences instead.
   - Each sentence packs several related facts together (e.g. a finding with its \
duration and trend, or a diagnosis with its medication and treatment setting) \
rather than spreading one fact per sentence — but it must still READ as a \
sentence, not as fragments glued together.
   - If everything will not fit inside the word cap, state FEWER findings \
properly rather than more findings as fragments. Cutting a minor finding is \
always better than degrading the prose.
   - Move through the picture in a natural order: presenting findings first, \
then family history, then current diagnoses/treatment, then goals, then \
lifestyle context — as one unbroken paragraph.
   - Quantify with the specifics present in the data (ages, durations, named \
relatives, medications, facility) instead of vague qualifiers.""",
    "markdown": """\
1. PRECONSULTATION SUMMARY — format as a compact list of dense MARKDOWN bullet \
points a doctor can scan, most critical first. No headings, no bold section \
labels, no "Label: value" tags — each bullet is a plain declarative clinical \
clause that reads as natural language.
   Target style:
   - Telegraphic, information-dense clinical register — each bullet a short \
declarative clause, minimal connective filler, the tone of a clinician's \
handover note.
   - Each bullet packs several related facts together (a finding with its \
duration and trend, or a diagnosis with its medication and setting) rather than \
one fact per bullet.
   - Order the bullets by criticality: presenting findings first, then current \
diagnoses and treatment, then goals, then lifestyle context.
   - Quantify with the specifics present in the data (ages, durations, named \
relatives, medications, facility) instead of vague qualifiers.
   - Use markdown bullets ("- ") only — no headings, no bold labels, no tables, \
no "Label: value" tags.""",
}

# Style-independent rules for section 1.
_SUMMARY_COMMON_RULES = """\
   Rules:
   - Open with ONE tight clause framing what the PATIENT came in for — the areas \
they flagged as relevant and their stated goals — clearly attributed to the \
patient's OWN ask, not to a clinician's plan or your recommendation. Lead with \
the flagged areas and fold the goals in, e.g. "Patient came in focused on \
Breathing & Lungs, Heart & Blood Pressure, and Diabetes, Weight & Metabolism, \
wanting to manage a known condition and prevent disease." Do NOT open with a bare \
planning verb like "Prioritising" or "Focusing on" that reads as the clinician \
deciding — make it the patient's request (e.g. "Patient came in wanting…", "The \
patient flagged … as what matters to them, aiming to…"). One brief clause only, \
natural language (never a "Goals: …; Areas: …" tag). Do NOT call these \
"categories". Separate the flagged areas with "and", each as one atomic unit — a \
label may itself contain a comma (e.g. "Diabetes, Weight & Metabolism"), so never \
let one area read as several. Omit the areas or the goals only if absent.
   - After that opening clause, give the patient's findings, leading with the \
most critical, weaving in how long each has been present and whether it is \
worsening or stable.
   - Then cover any current diagnoses, medications, and treatment setting; and \
notable lifestyle factors — each only if present in the data.
   - In the findings and everything after the opening clause, do NOT use a bare \
"Patient" or "The patient" subject that leaves a subjectless clause dangling as a \
grammatical fragment. Write in subjectless clauses and state each fact DIRECTLY, \
as the finding itself — not as something the patient said. Write "Persistent \
fatigue 6 months, worsening; currently on Metformin \
500mg BD" rather than "Patient High blood sugar 6 months", "Patient reports \
persistent fatigue", or "reports being on Metformin". No pronouns (he, she, \
they, his, her, their). No other personal details (no name).
   - Do NOT prefix facts with attribution or reporting verbs — no "patient \
reports", "reports", "states", "complains of", "notes", "mentions", "describes", \
"is said to". The whole input already comes from the patient, so that framing is \
redundant filler; give the clinical fact on its own.
   - Write everything as natural clinical language, NEVER as "Label: value" \
tags. Say "Prioritized goals are managing a known condition and disease \
prevention" and "Lifestyle is sedentary with frequent alcohol and short sleep", \
not "Goals: ...; Lifestyle: sedentary, Alcohol: frequent, Sleep: <5 hrs".
   - Do NOT create a heading or section title per health pattern; the patterns \
set the ordering, they are not labels to print.
   - Never mention confidence scores, percentages, or any internal scoring.
   - Never mention what is absent, normal, not found, or not reported.
   - Never tell the doctor what to do, what to check, or what to consider. \
State only what is recorded in the data.
   - If the profile contains nothing to summarize, return an empty string for \
this summary — never invent, pad, or apologise."""

# FORMAT knob (output_style) for section 2 (family-risk summary).
_FAMILY_FORMATS = {
    "paragraph": """\
2. FAMILY RISK SUMMARY — one concise continuous prose paragraph, plain text \
only (no headings, no markdown, no bullets).""",
    "markdown": """\
2. FAMILY RISK SUMMARY — a compact list of MARKDOWN bullet points, one bullet \
per relative written in natural language, each condition carrying that relative's \
age of onset for it, e.g. "- Father developed hypertension at over 60 and high \
cholesterol at 55–60". No headings, no "Relative: conditions" colon tags. Use \
markdown bullets ("- ") only.""",
}

# Style-independent rules for section 2.
_FAMILY_COMMON_RULES = """\
   Do not use the word "patient" at all in this summary — write entirely in \
subjectless clauses or refer to the family directly. Rules:
   - WRITE IT AS SENTENCES, NOT AS A LEDGER. This is prose a doctor reads, not a \
table serialized into text. NEVER use the "Relative — condition (onset X), \
condition (onset Y); Relative — ..." form: a line like "Father — hypertension \
(onset >60) and high cholesterol (onset >60); Mother — high cholesterol (onset \
50-60)" is exactly the ugly output to avoid. Say it the way a clinician would \
speak it: "Father developed hypertension and high cholesterol after 60; mother \
developed high cholesterol in her fifties and diabetes after 60." No em-dash \
ledgers, no parenthetical onset tags, no semicolon-delimited lists of conditions.
   - Name the affected relatives and the condition DIRECTLY. The hereditary \
nature is already implied by context, so do NOT wrap clauses in a filler frame \
like "family history shows signs of...", "hereditary risk of...", "signals of \
familial...", or "runs in the family". Give the relative and condition once, \
plainly.
   - CONSOLIDATE relatives, NOT ages. State each relative once and group their \
conditions together, and when several relatives share a condition name them \
together once ("both parents developed high cholesterol..."). Every \
relative-to-condition link in the data must survive — merge for brevity, never \
drop a pairing.
   - AGE = AGE OF ONSET, PER CONDITION. Each age band is the age at which that \
relative DEVELOPED that specific condition, NOT their current age. Fold the onset \
age for EACH condition into the sentence as words — "developed hypertension after \
60", "in her fifties" — never as a parenthetical tag. A relative can have \
different onset ages for different conditions; keep each condition's own onset age \
and never collapse them to a single per-relative age. Two different onset ages for \
the same relative are NOT a contradiction — they are different conditions.
   - Frame it as what is present in the family, NOT as a verdict on the patient. \
Do NOT state that the patient "is at high risk", "is at risk", or similar, and \
do NOT conclude anything about the patient's own likelihood — just name who in \
the family has what.
   - Each "family history for this condition" entry is already attached to one \
of the patient's own reported concerns — connect the affected relative to that \
specific condition faithfully, and do not invent links beyond what the data \
gives.
   - Do NOT mention absent family history, no-risk conditions, or empty fields.
   - Do NOT mention confidence scores or any internal scoring.
   - Do NOT tell the doctor what to do.
   - Keep it natural language and tight, but it must READ WELL — flowing clinical \
sentences, never a compressed ledger. HARD LIMIT: at most 44 words. If it would \
run longer, keep only the most significant hereditary conditions — drop a \
condition rather than degrade the prose into fragments, and never exceed the cap.
   - If there is no family history to report, return an empty string — never \
state that there is none, and never invent one.
   - Also set the boolean `family_risk_present`: true ONLY when the family \
history carries a hereditary signal genuinely worth the doctor's attention (a \
condition tied to one of the patient's own current concerns, or a clinically \
significant pattern). Set it false when there is nothing noteworthy — and in that \
case the `family_risk_summary` MUST be an empty string. The flag and the summary \
must agree: family_risk_present=false ⇔ empty summary."""

# Section 3 (quick_summary) — style-independent. A single short natural-language
# line, the doctor's five-second glance. Facts only, subjectless. Independent of
# the paragraph/markdown style knob (which governs sections 1 and 2 only).
_QUICK_SUMMARY = """\
3. QUICK SUMMARY (`quick_summary`) — one short line giving the same picture as \
the preconsultation summary, most critical first. Rules:
   - Natural, concise language — plain short clauses a clinician reads at a \
glance, separated by semicolons or commas. Not cryptic codes, but far shorter \
than the paragraph. e.g. "Worsening hypertension 8 years; elevated ALT; maternal \
type 2 diabetes."
   - State FACTS, not evidence — the finding itself, never how it is known or \
that it was reported. Write "worsening hypertension 8 years", not "reports \
hypertension" or "labs show hypertension".
   - SUBJECTLESS — no "patient", no "the patient", no pronouns (he/she/they/his/\
her/their). Begin directly with the finding.
   - Order by criticality; the single most pressing finding leads. Keep the \
specifics that matter (a value, duration, trend, or named relative), drop \
connective filler.
   - Identity-free, no attribution filler, no invented findings, no confidence \
scores; never tell the doctor what to do. Always one line.
   HARD LIMIT: at most 30 words. If it would run longer, keep only the most \
critical facts — never exceed the cap.
   - If there is nothing to summarize, return an empty string."""

_CLOSING = {
    "paragraph": """\
Write the two summaries as plain text only — no markdown, no headings, no \
bullet points, no asterisks. The quick summary is always a single keyword line. \
Be concise.""",
    "markdown": """\
Format the two summaries as compact markdown bullet lists as described above — \
dense bullet points only, no headings, no bold labels, no "Label: value" tags, \
no tables, no prose paragraphs. The quick summary is always a single keyword \
line, not a bullet list. Be concise.""",
}


def build_summary_system_prompt(
    output_style: str = "paragraph", output_size: str = "medium"
) -> str:
    """Compose the summaries system prompt for a given style/size combination.

    output_style selects the format (prose paragraph vs markdown bullets);
    output_size selects coverage (small/medium/large). "all" is handled by the
    orchestrator (it renders each concrete size), so it falls back to medium
    here if ever passed directly.
    """
    style = output_style if output_style in _SUMMARY_FORMATS else "paragraph"
    size = output_size if output_size in _COVERAGE else "medium"
    return "\n\n".join(
        [
            _SUMMARY_PREAMBLE,
            _COVERAGE[size],
            "Produce the following:",
            _SUMMARY_FORMATS[style],
            _SUMMARY_COMMON_RULES,
            _FAMILY_FORMATS[style],
            _FAMILY_COMMON_RULES,
            _QUICK_SUMMARY,
            _CLOSING[style],
        ]
    )


# Backwards-compatible default (paragraph / medium) for callers that still read
# the module-level constant.
SYSTEM_PROMPT = build_summary_system_prompt()

HUMAN_PROMPT = """\
Patient profile (findings pre-ordered by criticality):

{profile}

Produce the two summaries for this patient.\
"""

# ---------------------------------------------------------------------------
# Checklist probe REGISTER (versioned).
#
# The `probe:` line — its tone/register — is the most heavily tuned part of the
# checklist, so it is factored into NAMED registers you switch between with one
# selector. To roll a register forward or back INSTANTLY, either edit
# ACTIVE_CHECKLIST_REGISTER below or set the env var PRECONS_CHECKLIST_REGISTER
# (env wins). Every register stays in source, so a revert loses nothing and git
# keeps the deeper history. Each register supplies two fragments woven into BOTH
# the concern and wellness checklist prompts:
#   - probe_field: the description of the `probe:` output field
#   - extra_rule:  an extra bullet appended under "Rules:" (may be empty)
# To add a new register (e.g. "associate_v3"), add an entry here and point the
# selector at it — no other code changes.
# ---------------------------------------------------------------------------
_CHECKLIST_PROBE_REGISTERS: dict[str, dict[str, str]] = {
    # v1 — the original imperative direction (reads as a senior clinician's order).
    "imperative_v1": {
        "probe_field": (
            'a short imperative direction for the doctor — e.g. "Validate '
            'metabolic drivers", "Review thyroid status (maternal history)", '
            '"Assess sleep architecture". NOT a full question and NOT a '
            "restatement of the profile."
        ),
        "extra_rule": "",
    },
    # v2 — an associate briefing the doctor: actionable but deferential, and varied.
    "associate_v2": {
        "probe_field": (
            "a short, plain-language flag written the way an associate briefs the "
            "doctor before the visit — actionable but NEVER a command; the doctor "
            "always decides. Point to the concrete next step (a question to ask, a "
            "value to get, a cause to pin down), not a bare restatement of the "
            "finding, and keep it plain rather than jargon-dense. Examples: \"Is a "
            'cardiac cause the first thing to pin down here?"; "Amoxicillin '
            'against a recorded penicillin allergy — confirm before it '
            'continues?"; "Cholesterol still climbing six years into atorvastatin '
            '— is it doing its job?"; "One to sort out with the patient."'
        ),
        "extra_rule": (
            "- VARY the shape of every probe. Do NOT open successive probes with "
            "the same word or template (never a run of \"Assess…/Assess…\", "
            "\"Confirm…\", \"Review…\", \"Worth…\", \"Consider…\"); mix short "
            "questions with short statements so the list never reads as a form. "
            "The deference comes from the framing — these are flagged FOR the "
            "doctor to decide — NOT from a hedging word bolted onto each line, so "
            'do not repeat "worth"/"consider"/"may want to" down the list; treat '
            "each probe as its own fresh sentence, not a slot filled from a "
            "template.\n"
            "- NEVER stack two directive verbs into one probe joined by \"and\" "
            "(e.g. NOT \"Verify the recorded Penicillin allergy immediately and "
            "hold or review the current Amoxicillin prescription until "
            "reconciled\" — that reads as an order, not a flag). Say the SAME "
            "thing as a single flagged tension instead: \"Amoxicillin against a "
            'recorded penicillin allergy — confirm before it continues?" One '
            "flag, one thought — even for an urgent (red_flag_escalation) item; "
            "urgency changes the score, never the register.\n"
            "- The 'Detected gaps' list below is raw signal, not phrasing to "
            "reuse — if a gap's wording would read as an order lifted straight "
            "into the probe, that is a sign to rewrite it, not copy it."
        ),
    },
    # v3 — surface the tension only; the doctor owns the action entirely. No
    # prescribed workup, no "observation — imperative" structure, no directive
    # verbs anywhere. Each probe is either an open question or a plain flag.
    "associate_v3": {
        "probe_field": (
            "a short flag that NAMES the tension, gap, or finding and, where it "
            "reads naturally, poses it as an open question — nothing more. It must "
            "NOT tell the doctor what to do about it: the doctor owns the workup, "
            "the orders, and the plan entirely. State WHAT is notable and WHY it is "
            "in tension; never append the response. Keep it plain, not jargon-"
            "dense. Good: \"Amoxicillin on the med list against a recorded "
            'penicillin allergy — real, or a charting slip?"; "BP still drifting up '
            'after eight years on amlodipine 10mg — is it actually controlled?"; '
            "\"'Erectile difficulty: yes' recorded for a 58-year-old woman — likely "
            'a mis-entry?"; "Sleep pattern looks like the main driver of the '
            'fatigue." Bad (these PRESCRIBE and are forbidden): "... — get recent '
            'home and clinic BP readings and orthostatic checks"; "... — confirm '
            'the allergy details and whether it was started intentionally"; '
            '"Obtain an HbA1c"; "Review the antihypertensive regimen".'
        ),
        "extra_rule": (
            "- The probe surfaces the tension; the DOCTOR decides the action. "
            "Never write what to do about a finding — no prescribed test, value to "
            "obtain, medication change, or workup. If a probe would read as an "
            "instruction the doctor could tick off, it is wrong: strip the action "
            "and leave only the flagged tension (as a statement or an open "
            "question).\n"
            "- BAN the \"observation — imperative\" shape: a clause that states a "
            "finding, then a dash/semicolon, then a command telling the doctor what "
            "to do (\"... — get X\", \"... — confirm Y and obtain Z\"). The part "
            "after the dash must itself be part of the observation or an open "
            "question, NEVER a directive.\n"
            "- Do NOT use directive verbs aimed at the doctor anywhere in the "
            "probe: get, obtain, order, measure, check, confirm, verify, "
            "reconcile, review, assess, evaluate, ensure, start, stop, hold, "
            "repeat, screen, rule out. These make it an order. An open question "
            "(\"is it controlled?\", \"real or a charting slip?\") carries the same "
            "intent without commanding.\n"
            "- VARY the shape of every probe. Do NOT open successive probes with "
            "the same word or template, and do NOT lean on a repeated hedge "
            "(\"worth\"/\"consider\"/\"may want to\"); mix open questions with "
            "plain flag statements so the list never reads as a form. Each probe is "
            "its own fresh sentence.\n"
            "- One flag, one thought — even for an urgent (red_flag_escalation) "
            "item. Urgency changes the score, never the register; a red flag is "
            "still surfaced as a flag, not shouted as an order.\n"
            "- The 'Detected gaps' list below is raw signal, not phrasing to "
            "reuse — if a gap's wording would read as an order lifted into the "
            "probe, that is a sign to rewrite it, not copy it."
        ),
    },
}

ACTIVE_CHECKLIST_REGISTER = config("PRECONS_CHECKLIST_REGISTER", default="associate_v3")


def _probe_register() -> dict[str, str]:
    """The active checklist probe register (falls back to associate_v3)."""
    return _CHECKLIST_PROBE_REGISTERS.get(
        ACTIVE_CHECKLIST_REGISTER, _CHECKLIST_PROBE_REGISTERS["associate_v3"]
    )


_PROBE_FIELD = _probe_register()["probe_field"]
_PROBE_RULE = _probe_register()["extra_rule"]
# Appended verbatim under "Rules:"; empty register -> no extra bullet.
_PROBE_RULE_BLOCK = f"\n{_PROBE_RULE}" if _PROBE_RULE else ""

# Register-INDEPENDENT rule (holds whichever probe register is active): the probe
# must read on its own, without the reason. It leads with the concrete patient
# anchor that triggered it, and stays the SAME length by trading generic filler
# for that anchor — so this never grows the probe. Woven into both checklist
# prompts right under the `probe` field.
_PROBE_SELF_CONTAINED = (
    "   The probe MUST stand on its own: a doctor who reads ONLY the probe (never "
    "the reason) should grasp BOTH what triggered it and what is being asked. Lead "
    "with the concrete patient ANCHOR — the specific finding, value, duration, "
    "goal, or gap that motivated it — not a generic category. E.g. NOT "
    '"Vaccination and sexual-health screening documented?" but "Disease-prevention '
    'a stated goal — routine immunizations and STI screening up to date?"; NOT "No '
    'baseline sleep metrics — sleep diary available?" but "Unrefreshing sleep '
    'despite 7-8h plus a sleep goal — any wearable/diary baseline to track '
    'against?". Do NOT lengthen the probe to fit the anchor — pay for it by '
    "cutting generic/filler words. The reason only justifies; it must never be "
    "needed to understand the probe.\n"
    "   HARD LIMIT: the probe is at most 20 words. If it would run longer, cut "
    "filler and keep the anchor plus the ask — never exceed the cap.\n"
    "   PLAIN LANGUAGE ONLY: never surface internal identifiers, field names, "
    "codes, cluster/pattern ids, or ALL-CAPS/snake_case tokens from the data "
    '(e.g. "ACTIVITY_SEDENTARY", "cluster_3", "risk patterns list ..."). '
    'Translate every such token into ordinary clinical words — say "a sedentary '
    'pattern", not "ACTIVITY_SEDENTARY" — in BOTH the probe and the reason.\n'
    "   THE QUESTION MARK MUST NOT BE LOAD-BEARING: if the probe ends in \"?\", its "
    "grammar alone (an auxiliary/interrogative word — is/are/does/any/what/how/"
    "whether/could) must already signal a question BEFORE the reader reaches the "
    "final mark, so losing that one character never flips a question into a "
    "flat assertion of the opposite. NOT a declarative clause with a \"?\" bolted "
    'on: "...bedtime routine, caffeine, alcohol, or late screens contributing?" '
    'reads as a STATEMENT that they ARE contributing if the "?" is missed — say '
    '"...is a bedtime routine, caffeine, alcohol, or late screens contributing?" '
    'instead. Likewise NOT "...any witnessed snoring, gasping, or daytime '
    'sleepiness?" (a bare list) — say "...has anyone witnessed snoring, gasping, '
    'or daytime sleepiness?". Every question-form probe needs its own '
    "interrogative word or auxiliary verb, not just a trailing mark."
)


CHECKLIST_SYSTEM_PROMPT = f"""\
You are a clinical pre-consultation assistant generating a probe checklist for \
a doctor. The doctor uses this checklist in the consultation to decide where to \
dig deeper. Your job is to examine the patient's reported concerns and health \
patterns and decide what warrants probing along one or more of these axes.

{prompt_fragments.build_demographics_instruction("checklist")}

How to read the input (the labels tell you what each value means) — each \
reported concern lists how it "affects daily life", its "duration", its "trend", \
the "symptoms", how the patient "knows" it, its "family history for this \
condition", and validation answers ("reported yes to" / "answered no to"); each \
health pattern lists the lifestyle factors driving it. Mine these for \
probes: a severe/worsening concern with high daily-life impact feeds \
"red_flag_escalation"; two facts that cannot both be MEDICALLY true (reconciling \
them needs clinical judgment) feed "contradiction_resolution"; a record that \
looks mis-entered or unlinked (a data-capture error, verify with the patient) \
feeds "factual_discrepancy"; thin evidence, an \
unvalidated pattern, or a weakly-supported concern feed "missing_context" and \
"diagnostic_clarification"; a worsening trend on a concern tied to a \
diagnosis/medication feeds "treatment_efficacy"; lifestyle factors that undercut \
a regimen feed "medication_adherence" or "lifestyle_driver". Treat an "answered \
no to" item as a signal ONLY when it is a clinically meaningful pertinent negative.

The probing axes:
- "red_flag_escalation": does this concern look potentially urgent or dangerous \
(severe/worsening with high daily-life impact) and need to be clarified first?
- "contradiction_resolution": do two CLINICAL facts genuinely conflict — they \
cannot both be MEDICALLY true and reconciling them takes clinical judgment (e.g. \
a concern that contradicts another concern, or a symptom pattern or duration that \
contradicts a stated diagnosis or its own trend)? Litmus: "which of these is \
medically correct?" This is NOT for concerns that merely need confirming, are \
weakly supported, or are unvalidated — those are "diagnostic_clarification" or \
"missing_context". Use sparingly, only for a true clinical conflict.
- "factual_discrepancy": is the RECORD itself mis-entered, incomplete, or \
unlinked — a likely data-capture problem rather than a medical conflict (e.g. a \
medication with no matching diagnosis on the problem list, or a field recorded \
with two different values for the same item)? Litmus: "did we write this down \
correctly?" It just needs the patient to confirm the fact, NOT clinical \
reasoning (if it takes clinical judgment, it is "contradiction_resolution"). \
NEVER raise it for a relative's differing family-history ages — those are age of \
onset per condition and are normal.
- "risk_refinement": could family history or a comorbidity make this more \
(or less) serious than it looks in isolation?
- "treatment_efficacy": for a concern tied to a current diagnosis/medication, is \
the treatment actually working given the trend (e.g. worsening despite therapy)?
- "diagnostic_clarification": is this concern's link to its health pattern (or \
its stated interpretation) actually real rather than coincidental, and worth \
confirming?
- "missing_context": is the evidence, history, or trend thin — what is missing \
that could change the picture?
- "medication_adherence": is there a signal the patient may not be taking the \
prescribed medication/regimen for this concern?
- "lifestyle_driver": is a modifiable lifestyle factor (sleep, diet, activity, \
stress) plausibly driving this concern and worth addressing?

For each warranted probe, emit a hypothesis with:
- tag: one of the axes above (use the exact wording / underscores).
- probability: 0.0-1.0 estimate that this probe is warranted and will surface \
something clinically useful. Be calibrated — reserve high values for strong \
signals.
- probe: {_PROBE_FIELD}
{_PROBE_SELF_CONTAINED}
- reason: one or two sentences stating the specific clinical concern or data \
signal that justifies this probe. Be concrete — name the concern, the signal, \
the gap, or the conflict that triggered it.

Rules:
- Examine every reported concern and health pattern. Generate multiple \
hypotheses when more than one axis applies.
- Probe scoring/ordering is computed downstream — you only assign the axis.
- State the signal DIRECTLY — no attribution or reporting filler ("patient \
reports", "reports", "states", "complains of", "mentioned in report", "family \
history shows", "hereditary risk of"). Name the finding, relative, or lifestyle \
factor itself (e.g. "Worsening cholesterol over 3 years; mother affected \
50-60"), not the fact that it was reported.
- Never mention confidence scores, percentages, or any internal scoring anywhere \
in the output — neither in the probe nor the reason.{_PROBE_RULE_BLOCK}\
"""

WELLNESS_CHECKLIST_SYSTEM_PROMPT = f"""\
You are a clinical pre-consultation assistant generating a probe checklist for \
a doctor. This patient has no pressing or high-criticality findings — they are \
broadly healthy. Your job is NOT to hunt for hidden disease. Instead, examine \
the profile and surface proactive, wellness-oriented directions the doctor can \
use to keep this patient healthy. Decide which health patterns (or the patient \
overall) warrant a probe along one or more of these axes. Read the input labels \
as plain clinical language, not as system fields.

The probing axes:
- "factual_discrepancy": is the RECORD itself mis-entered, incomplete, or \
unlinked — a likely data-capture error to verify with the patient (e.g. a \
medication with no matching diagnosis, or a field recorded with two different \
values for the same item)? Litmus: "did we write this down correctly?" It needs \
the patient to confirm the fact, not clinical reasoning. NEVER raise it for a \
relative's differing family-history ages — those are age of onset per condition \
and are normal.
- "preventive_screening": an age- and family-history-appropriate screening that \
is worth discussing even though the patient is asymptomatic.
- "early_risk_surveillance": a family-history or lifestyle risk that has not \
yet produced a finding but is worth proactively monitoring.
- "baseline_establishment": a measurement or marker worth capturing now, while \
healthy, to establish a personal baseline for future comparison.
- "lifestyle_optimization": an already-acceptable habit (sleep, activity, diet, \
stress) that could be reinforced or fine-tuned for better long-term outcomes.
- "goal_alignment": a direction tied to the patient's stated goals \
(energy, fitness, performance, longevity) rather than to any disease.

For each warranted probe, emit a hypothesis with:
- tag: one of the axes above (use the exact wording / underscores).
- probability: 0.0-1.0 estimate that this probe is worth the doctor's time. Be \
calibrated — reserve high values for clearly valuable, well-grounded directions.
- probe: {_PROBE_FIELD}
{_PROBE_SELF_CONTAINED}
- reason: one or two sentences stating the specific signal — a family-history \
pattern, a stated goal, or a lifestyle factor — that makes this worthwhile.

Rules:
- Stay proactive and preventive. Do NOT manufacture concerns or imply the \
patient is unwell.
- State the signal DIRECTLY — no attribution or reporting filler ("patient \
reports", "reports", "states", "mentioned in report", "family history shows", \
"hereditary risk of"). Name the goal, relative, or lifestyle factor itself \
(e.g. "Paternal diabetes; no baseline HbA1c on record"), not the fact that it \
was reported.
- Never mention confidence scores, percentages, or any internal scoring anywhere \
in the output — neither in the probe nor the reason.{_PROBE_RULE_BLOCK}\
"""

CHECKLIST_HUMAN_PROMPT = """\
Patient demographics: {age}yo {gender}

Patient profile (findings pre-ordered by criticality):

{profile}

Detected gaps (raw signals only — rewrite each in your own words and register \
below; never copy this wording into a probe verbatim):
{seeds}

Produce the probe hypotheses for this patient.\
"""


# ---------------------------------------------------------------------------
# Second pass: reorder the already-written summaries by priority.
#
# The summaries call writes the prose; these prompts re-sequence it so the most
# critical information leads, WITHOUT rewriting it. The register, format, and
# every fact of the first output must survive into the reordered output — only
# the order changes.
# ---------------------------------------------------------------------------

# The reorder pass must PRESERVE whichever format the summaries call produced,
# so its format-preservation clause is style-parameterized.
_REORDER_SUMMARY_FORMAT_CLAUSE = {
    "paragraph": """\
one continuous prose paragraph; telegraphic, information-dense clinical handover \
style; subjectless clauses; no markdown, no headings, no bullets, no line breaks""",
    "markdown": """\
the same compact list of dense markdown bullet points; telegraphic, \
information-dense clinical handover style; subjectless clauses; markdown bullets \
only, no headings, no bold labels, no "Label: value" tags, no prose paragraph, \
no tables""",
}

_REORDER_FAMILY_FORMAT_CLAUSE = {
    "paragraph": """\
one concise continuous prose paragraph; plain text only (no markdown, headings, \
or bullets)""",
    "markdown": """\
a compact list of markdown bullet points, one bullet per relative in natural \
language listing that relative's conditions (markdown bullets only, no heading, \
no colon tags, no prose paragraph)""",
}


def build_reorder_summary_system_prompt(output_style: str = "paragraph") -> str:
    style = output_style if output_style in _REORDER_SUMMARY_FORMAT_CLAUSE else "paragraph"
    return f"""\
You reorder an already-written clinical pre-consultation summary so the most \
critical information comes first. You are given the SUMMARY and a PRIORITY ORDER \
(the patient's findings ranked most-critical-first, each tagged HIGH/MODERATE/LOW).

Your job is to RE-SEQUENCE and lightly CONSOLIDATE the existing content — not to \
rewrite it. Strict rules:
- Keep the brief opening clause (the areas the patient flagged as relevant, with \
their goals folded in) at the very START, unchanged. Then lead with the \
highest-priority (HIGH) findings, descending through MODERATE to LOW; keep facts \
about the same finding together. Other non-finding context (diagnoses, \
medications, treatment setting, lifestyle) follows the findings, as in the \
original.
- CONSOLIDATE (club the details): if the same finding, diagnosis, medication, or \
entity is referred to in more than one place, merge those into a single mention \
holding all its facts, rather than repeating the subject. Club related facts so \
nothing is stated twice.
- Do NOT change wording, facts, numbers, durations, trends, or clinical \
phrasing. Reuse the original sentences and clauses verbatim wherever possible; \
you may re-sequence and merge them and minimally adjust connective words so it \
still flows.
- MOVE WHOLE SENTENCES, NEVER A DANGLING FRAGMENT. If two clauses in the \
original are joined by a semicolon or comma into one sentence, treat that as one \
indivisible unit unless you are merging it with another mention of the exact \
same finding — do not relocate only the first half and leave the join mark \
(";" or ",") stranded in front of an unrelated sentence. When you place a clause \
at a new position, terminate it with a period before the next clause begins, and \
re-check every semicolon and comma in your output actually still joins two parts \
of the SAME original sentence.
- Do NOT add any new fact, finding, or interpretation, and do NOT drop any fact \
present in the original. Merging may remove a duplicate mention, never a fact.
- Preserve the EXACT register and format of the original: {_REORDER_SUMMARY_FORMAT_CLAUSE[style]}; \
no pronouns (he, she, they, his, her, their); the word "Patient" or "The \
patient" at most once, at the very start.
Return only the reordered summary.\
"""


REORDER_SUMMARY_HUMAN_PROMPT = """\
PRIORITY ORDER (most critical first):
{priority_order}

SUMMARY to reorder:
{summary}

Return the reordered summary, in the same format as the input.\
"""


def build_reorder_family_risk_system_prompt(output_style: str = "paragraph") -> str:
    style = output_style if output_style in _REORDER_FAMILY_FORMAT_CLAUSE else "paragraph"
    return f"""\
You reorder AND consolidate an already-written FAMILY-RISK summary so the \
hereditary signals most relevant to THIS patient come first and no relative or \
condition is repeated. You are given the SUMMARY and a PRIORITY ORDER of \
hereditary conditions.

Do two things — re-sequence, then club the details together. Strict rules:
- ORDER: surface the conditions marked DIRECTLY RELATED to the patient's own \
current health patterns EARLIEST, in the order given; then the remaining \
hereditary signals by descending risk.
- CONSOLIDATE relatives, NOT ages: the input often repeats the same relative \
across separate clauses — collapse that so each relative is named once and their \
conditions grouped together, and when several relatives share a condition name \
them together once. For example, rewrite "Father: hypertension. Father: \
hypercholesterolemia. Mother: high blood sugar." as "Father developed \
hypertension at over 60 and hypercholesterolemia at 55–60; Mother developed high \
blood sugar at over 60."
- AGE = AGE OF ONSET, PER CONDITION: each age band is the age at which that \
relative DEVELOPED that specific condition, NOT their current age. Keep the onset \
age attached to EACH condition and never collapse a relative's conditions to one \
shared age. Different onset ages for the same relative are expected (different \
conditions) — never treat them as a conflict and never drop one.
- Do NOT drop or invent any relative, onset age, condition, or relative-to-\
condition link. Merge purely for brevity; EVERY pairing (with its onset age) \
present in the input must still be recoverable from your output.
- Keep relatives and conditions named directly, with NO filler frame ("family \
history shows signs of...", "hereditary risk of...", "runs in the family") and \
NEVER a verdict on the patient ("is at high risk"); the word "patient" must NOT \
appear anywhere.
- Format: {_REORDER_FAMILY_FORMAT_CLAUSE[style]}.
Return only the reordered, consolidated family-risk summary.\
"""


REORDER_FAMILY_RISK_HUMAN_PROMPT = """\
PRIORITY ORDER (conditions directly related to the patient first, then by risk):
{priority_order}

FAMILY-RISK SUMMARY to reorder:
{summary}

Return the reordered family-risk summary, in the same format as the input.\
"""

# Backwards-compatible defaults (paragraph) for callers reading the constants.
REORDER_SUMMARY_SYSTEM_PROMPT = build_reorder_summary_system_prompt()
REORDER_FAMILY_RISK_SYSTEM_PROMPT = build_reorder_family_risk_system_prompt()


def render_seeds(seeds: list[str]) -> str:
    if not seeds:
        return "(none detected — derive follow-ups from the profile)"
    return "\n".join(f"- {s}" for s in seeds)


# ---------------------------------------------------------------------------
# Document insight extraction (extract_insights.py)
#
# Two LLM calls are made per document:
#   1. Image-read call — IMAGE_READ_PROMPT — transcribes an embedded image,
#      scan, chart, or figure into faithful text so it can be slotted back into
#      the document at its native location.
#   2. Insight call — INSIGHT_SYSTEM_PROMPT + INSIGHT_HUMAN_PROMPT — reads one
#      page of redacted, block-id-annotated text and returns the few
#      patient-specific insights worth a doctor's attention before consulting.
# ---------------------------------------------------------------------------

IMAGE_READ_PROMPT = """\
You are reading one image taken from a medical report (a scan, photo, chart, \
graph, table, figure, or diagram). Produce two things from it:

1. TEXT (OCR) — transcribe ALL visible text, labels, values, and units exactly \
as shown. For a table, preserve rows and columns using tabs/spaces so the \
structure is clear. Do not summarize, interpret, diagnose, or add anything not \
visible.

2. NON-TEXT OBJECTS — for any visual content that is NOT plain text (a chart, \
graph, plot, anatomical diagram, scan/photo of the body, or figure), add ONE \
very brief, precise description line prefixed with "[FIGURE] ". State only what \
is objectively visible — the kind of object, its title/axes/series if a chart, \
and the concrete data points or trend shown; or the body region and what is \
depicted if a scan/photo. Keep it to a single tight sentence. Do NOT diagnose, \
infer, or speculate beyond what is plainly shown.

Output the OCR text first, then any "[FIGURE] " lines. If the image carries no \
readable text and no meaningful non-text object, return an empty string.\
"""

INSIGHT_SYSTEM_PROMPT = """\
You are a clinical pre-consultation assistant. A doctor reads your output in \
the final minute before seeing a patient to know what to probe into. From ONE \
page of a patient's uploaded report, extract (a) the few insights that are \
specific to THIS patient and worth the doctor's attention, and (b) EVERY \
biomarker measurement present on the page. Use minimal words. Never invent \
values or findings not present in the text.

You are given the page as a list of text BLOCKS, each with a BLOCK_ID.

BIOMARKERS (`biomarkers`): for EVERY lab/biomarker measurement on the page — in \
range OR out of range — emit one entry with:
  - `name`: the analyte, e.g. "ALT", "Haemoglobin", "LDL cholesterol".
  - `value`: the NUMERIC measured value ONLY, e.g. "56", "6.1", "13.5". Strip any \
lab abnormality flag or marker printed next to it — "*H", "*L", "H", "L", "HH", \
"↑", "↓", "*", "(High)". Write "6.1", NEVER "6.1 *H". Put the high/low \
information in `status`, not in `value`.
  - `unit`: its unit if printed, e.g. "U/L", "g/dL"; null if none.
  - `reference_range`: the reference/normal range EXACTLY as printed on the page, \
e.g. "7-40", "<200", "13.0-17.0"; null if the page prints none.
  - `status`: "high" if the value is above its range, "low" if below, "normal" \
if within. Use the printed reference range when present; otherwise judge against \
the universal/standard adult range for that analyte. Capture EVERY measurement, \
not only abnormal ones (the flag for "report has biomarkers" depends on it).

Extract insights of these kinds only:

1. ABNORMAL MEASUREMENTS (category "abnormal_measurement") — pick ONLY \
measurements that are strictly above or strictly below the universal/standard \
reference range for that analyte (true for any human, ignore patient \
demographics). Return AT MOST TWO measurement insights for the page: one titled \
"High measurements" whose content lists every out-of-range-high value together \
in a single short paragraph with its number and unit, and one titled "Low \
measurements" listing every out-of-range-low value together with number and \
unit. Omit either if empty. Never include in-range/normal values. (These feed \
the narrative summary; the structured `biomarkers` list above is separate and \
must still include ALL measurements.)

2. CLIENT-SPECIFIC FINDINGS — keep only statements clearly about THIS client \
(not generic textbook explanations). Choose the most specific category:
   - "diagnosis": a stated/established diagnosis or condition.
   - "imaging_finding": an observation from a radiology/imaging study \
(X-ray, CT, MRI, ultrasound, scan).
   - "clinical_finding": any other client-specific examination or report \
finding that is not a lab value or an imaging result.
   - "symptom": a symptom the client reports or that the report attributes to \
the client.
   DROP generic background (e.g. "this enzyme regulates X").

3. MEDICATIONS & PROCEDURES — "medication": a drug the client is on or being \
started on; "procedure": a procedure/surgery the client has had or is scheduled \
for.

4. RECOMMENDATIONS (category "treatment_recommendation") — when a recommendation \
is given with reasons, how-to, or explanation, keep ONLY what is recommended. \
Strip the rationale and instructions.

5. CHECKLISTS / MONITORING (category "monitoring_plan") — if the report provides \
a checklist or a set of things to monitor or follow up, collapse it to one \
insight: "A checklist of monitoring X, Y, Z".

6. RISK FACTORS (category "risk_factor") — a client-specific risk factor the \
report flags (e.g. family history, exposure, modifiable risk) that is not \
itself a current finding or diagnosis.

DO NOT INCLUDE (in insights): generic information, textbook explanations, \
normal/in-range values, or routine demographic detail (name, age, gender). If \
the page has nothing patient-specific worth flagging, return an empty insight \
list. (Normal biomarker values are still captured in the `biomarkers` list — the \
"no normal values" rule applies to the narrative insights only.)

Each insight: a short `title`, a `category` (one of abnormal_measurement, \
symptom, clinical_finding, imaging_finding, diagnosis, medication, procedure, \
treatment_recommendation, monitoring_plan, risk_factor), and minimal-words \
`content`.

State every finding DIRECTLY. Never begin with or include meta-phrasing such as \
"the report shows/indicates/tells/states/reveals/notes", "mentioned in report", \
"documented in", "as per the report", "the document ...", "this report ...", or \
patient-attribution filler like "patient reports"/"reports". Write the clinical \
fact itself, not a description of the report describing it (write "ALT elevated \
at 56 U/L", not "the report shows ALT is elevated" or "ALT elevation mentioned \
in report").\
"""

INSIGHT_HUMAN_PROMPT = """\
Report page {page} — text blocks:

{blocks}

Extract the patient-specific insights for this page.\
"""

CONSOLIDATE_SYSTEM_PROMPT = f"""\
You are consolidating the individual facts extracted from a multi-page medical \
report into a short report `title` plus ONE tight `summary` paragraph a doctor \
can scan in seconds before a consultation.

You are given the patient's age and gender, and a list of raw facts, each with a \
CATEGORY, PAGE, and CONTENT (already ordered roughly most-weighty-first).

First, the `title`: a short 2-6 word name for WHAT THIS REPORT IS, so a doctor \
knows its type at a glance — e.g. "Comprehensive Metabolic Panel", "Thyroid \
Function Panel", "Organic Acids Test (OAT)", "Gut Microbiome Analysis (16S \
rRNA)", "Thyroid Ultrasound". Infer it from the analytes/findings present (a \
panel of liver+kidney+glucose+electrolytes is a "Comprehensive Metabolic Panel"; \
TSH/T3/T4 is a "Thyroid Function Panel"; an imaging description is the study, e.g. \
"Thyroid Ultrasound"). Name only the report type — no patient identifiers, no \
findings, no dates. Return an empty string if the document has no identifiable \
clinical content.

Then the `summary`: a single paragraph stating the VISIBLE issues in the report \
— the objective findings actually present, with their measured values — and \
NOTHING you infer on your own. Rules:
- READ LIKE A CLINICIAN WROTE IT, NOT LIKE A SPREADSHEET. Write complete, \
flowing sentences with real verbs, the way a doctor would describe the report to \
a colleague. NEVER a chain of "analyte value flag" fragments strung together with \
semicolons or commas. WRONG (a keyword/value ledger): "HbA1c 6.1% high; fasting \
glucose 112 mg/dL; vitamin D 8 ng/mL low; LDL 145 mg/dL." RIGHT (natural prose): \
"HbA1c is mildly elevated at 6.1% and fasting glucose sits in the prediabetic \
range at 112 mg/dL. Vitamin D is severely deficient at 8 ng/mL, and LDL is \
borderline high at 145 mg/dL against a low HDL of 38." Same facts, same numbers — \
but sentences a person can read aloud.
- VISIBLE ISSUES ONLY, NO SPECULATION: report only what the findings objectively \
state. Do NOT add your own interpretation, diagnosis, mechanism, cause, risk \
judgment, or any conclusion the report itself did not state. If the report gives \
a value, give the value; do not explain what it "means" beyond what is written. \
(Describing a value as "elevated", "low", or "within range" is fine — that is the \
finding itself, not an inference.)
- INCLUDE THE MEASUREMENTS: every quantitative finding keeps its number and unit, \
woven into the sentence — "HbA1c is elevated at 6.1%", "ALT is high at 56 U/L", \
"vitamin D is severely deficient at 8 ng/mL". A lab summary without its numbers is \
unacceptable, but the numbers live inside sentences, never as bare tags.
- PRIORITIZE: lead with the most abnormal or clinically critical findings — \
out-of-range values, red-flag findings, acute or active diagnoses — then the \
moderate ones, then the minor/informational. The first sentence carries what \
matters most.
- CONDENSE by MERGING, not by dropping grammar: combine facts about the SAME \
clinical subject (same organ, study, analyte group) into one sentence; never \
repeat a finding. If everything will not fit the word cap, state FEWER findings \
as proper sentences rather than more findings as fragments.
- Demographic sanity: a finding clearly incompatible with or extremely atypical \
for the patient's age/gender is likely a data error — mention it LAST (or as \
needing verification), never lead with it.

{prompt_fragments.build_demographics_instruction("insight")}
Strict content rules:
- Use ONLY language that appears, verbatim or very closely paraphrased, in the \
source facts. No inferences and no hedged language ("could", "may", "suggest", \
"possible", "likely", "consistent with") unless the report itself used it.
- Prefer stating facts DIRECTLY, but an occasional natural report-framing is \
fine for readability — "the report notes a low vitamin D" or "the panel shows an \
elevated ALT" reads well ONCE. Do NOT overuse it: never open more than one \
sentence that way, and never let "the report shows/indicates/reveals", "mentioned \
in report", "documented in", or "as per the report" become a repeated crutch on \
every clause. Vary the phrasing; most findings should simply be stated ("ALT is \
elevated at 56 U/L"). Never use patient-attribution filler ("patient \
reports"/"reports").
- Do NOT tell the doctor what to do, and do NOT invent content beyond the facts.
- Write flowing clinical prose (no bullet list, no headings, no page numbers).
- HARD LIMIT: at most 75 words. If it would run longer, keep the most critical \
findings with their values as proper sentences and drop the least important — \
never buy space by collapsing prose into fragments, and never exceed the cap.
- If there are no patient-specific facts at all, return an empty string.

Before anything else, judge `has_findings`:
- Set `has_findings` to false if the raw facts you were given do NOT amount to \
genuine, coherent, patient-specific clinical content — for example the facts \
look garbled, contradictory, describe something implausible for a medical \
report, or plainly came from a misread image rather than real report content. \
When `has_findings` is false, still fill in `title`/`summary` as best you can, \
but they will be discarded and treated as empty — so do not worry about getting \
them perfect in that case.
- Otherwise (the normal case) set `has_findings` to true.

Finally, the criticality flag:
- `is_flagged`: true ONLY if this document contains something clinically \
critical the doctor must not miss before the consultation — e.g. a markedly \
out-of-range value, a red-flag imaging finding, an acute or serious active \
diagnosis, or an urgent recommendation. Routine, in-range, or minor \
informational content is NOT flagged. Judge conservatively: reserve the flag for \
findings that genuinely change what the doctor should address first. (A \
non-medical document — e.g. a diet plan — can still be flagged if it states \
something clinically critical.) Never true when `has_findings` is false.
- `flag_reason`: a brief, HIGH-LEVEL phrase (under ~10 words) naming the KIND of \
critical finding — NOT an exhaustive list of values, e.g. "Markedly elevated \
HbA1c and lipid panel", "Red-flag imaging finding", "Uncontrolled diabetes \
markers". If `is_flagged` is false, return an empty string.\
"""

CONSOLIDATE_HUMAN_PROMPT = """\
Patient demographics: {age}yo {gender}

Raw facts from this report (roughly most-weighty first):

{formatted_facts}

Give the short report `title` (what this report IS) and the single prioritized \
`summary` paragraph — most abnormal/critical findings first, mentioning LAST (or \
as needing verification) any finding genuinely incompatible with this patient's \
age/gender. Judge `has_findings` (do these facts represent genuine clinical \
content). Then decide `is_flagged` (does this contain something clinically \
critical the doctor must not miss) and give the brief, high-level `flag_reason`.\
"""


# ---------------------------------------------------------------------------
# Document metadata extraction (extract_insights.py)
#
# A single per-document call over the opening pages that pulls two document-LEVEL
# facts: the date the document was created/issued and the facility/author that
# issued it. Deliberately generic — a diet plan, letter, or discharge note all
# carry these, so this is NOT gated on the file being a medical report.
# ---------------------------------------------------------------------------

DOC_METADATA_SYSTEM_PROMPT = """\
You extract two pieces of DOCUMENT-LEVEL metadata from the opening pages of an \
uploaded document: the date it was created/issued, and the facility or author \
that created/issued it. This applies to ANY document — a lab report, an imaging \
report, a discharge summary, a diet plan, a doctor's letter — not only medical \
reports.

You are given the document's first pages as a list of text BLOCKS.

Multiple candidates are common. Find EVERY candidate first, then choose the \
single best of each.

DATE:
- List every date you see in `date_candidates`, each tagged with the label the \
document gave it, e.g. "Reported On: 2024-03-12", "Collected: 2024-03-10", \
"Printed: 2024-03-13".
- Then set `report_date` to the ONE that best represents when the document was \
produced. Prefer, in order: a report / issue / "reported on" date > a \
sample-collection date > a print date > any other single date.
- NEVER use the patient's date of birth, an appointment or follow-up date, or a \
reference-range validity date.
- Normalise `report_date` to ISO YYYY-MM-DD. If only month and year are given, \
use the first day of that month. If no usable date exists, set it to null.

LOCATION:
- List every organisation or person that could be the issuer in \
`location_candidates`, each tagged with its role, e.g. "Issuing lab: ABC \
Diagnostics", "Hospital: XYZ Medical Center", "Referring: Dr A".
- Then set `report_location` to the ONE that CREATED / ISSUED the document — the \
letterhead lab, clinic, hospital, or author. Do NOT use a referring physician, \
the patient's home address, or a device/manufacturer brand name.
- If no issuer is stated, set `report_location` to null.

Extract only what is present. Never invent a date or a facility the text does \
not contain.\
"""

DOC_METADATA_HUMAN_PROMPT = """\
Document opening pages — text blocks:

{blocks}

List all date and location candidates, then select the single best creation \
date and issuing location.\
"""
