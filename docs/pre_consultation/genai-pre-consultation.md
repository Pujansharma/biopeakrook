# Pre-consultation Intelligence Engine

Two independent capabilities are:

1. **Preconsultation Summary** — turns pre-consultation form data into clinical briefs, family risk assessments, and scored probe checklists
2. **Insight Extraction** — distills patient documents (PDFs, scans, reports) into page-cited, necessity-scored clinical findings


---

## Environment Variables


### LLM & API Credentials

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | string | (none) | OpenAI API key for ChatOpenAI (required for live LLM calls; omit for `mock=True` mode) |
| `LANGFUSE_PUBLIC_KEY` | string | (none) | Langfuse public key for trace logging |
| `LANGFUSE_SECRET_KEY` | string | (none) | Langfuse secret key for trace logging |
| `LANGFUSE_HOST` | string | `https://cloud.langfuse.com` | Langfuse server URL (or localhost for local tracing) |

### Webhook Configuration

`asummarize_patient` / `summarize_patient` can notify the **legacy backend** that
a patient's pre-consultation form has been received. This is a one-way,
fire-and-forget POST of the **raw input form** (not the generated summary/
checklist) — it fires immediately when the call starts, before any LLM work, so
the legacy backend learns "this patient's form came in" regardless of whether
summarization later succeeds or fails.

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `TOOLS_URL` | string | `http://localhost:8000` | Base URL of the **legacy backend** that receives the webhook |
| `PRECONS_TOOL_TRIGGER_API` | string | `/preconsultation/v1/onboarding-webhook` | Endpoint path appended to `TOOLS_URL` for the webhook POST |
| `ONBOARDING_WEBHOOK_SECRET` | string | (none) | HMAC-SHA256 signing secret for the webhook payload (optional; if set, the POST is signed via an `X-Onboarding-Signature` header so the legacy backend can verify authenticity) |

Behavior, from [summarize.py](summarize.py):
- Runs on a background daemon thread ([`_fire_webhook`](summarize.py)) — the response is never awaited, so a slow or dead legacy backend never blocks or fails the summarize call.
- Any POST failure (timeout, connection error, non-2xx) is caught and only logged (`logger.warning`) — it is invisible to the caller.
- Skipped entirely when `mock=True`, or when the caller passes `trigger_webhook=False` (recommended for local/offline runs, or you'll get connection errors against a legacy backend that isn't reachable).


---


## 1. Onboarding Summary — `summarize_patient` / `asummarize_patient`

Use this when you have a **v3 pre-consultation form export** (`directive_schema_id
3.0.1`) and want the doctor's pre-read. Both functions share the same signature
and return the same shape.


```python
from intelligence_engine.preconsultation import summarize_patient, asummarize_patient

# sync
result = summarize_patient(form, trigger_webhook=False)

# async (native coroutine — use inside an async context)
result = await asummarize_patient(form, trigger_webhook=False)

# larger / bulleted output
result = summarize_patient(form, output_style="markdown", output_size="large", trigger_webhook=False)
```

| Argument | Type | Required? | Notes |
| --- | --- | --- | --- |
| `client_details` | `dict` | **Required** | Pre-consultation form. Required top-level keys: `patient_baseline`, `concerns`, `medical_history`, `cluster_scores`, `health_goals`, `lifestyle_answers`. Missing any of these — or a missing/empty `patient_baseline.id` — raises `ValueError`. See full annotated schema below. |
| `llm` | LangChain chat model | Optional (default `None`) | Leave unset to use the per-task config. When set, overrides model/config entirely. |
| `model` | `str` | Optional (default `None`) | Model name override (e.g. `"gpt-4o"`). Takes precedence over config but not over `llm`. Leave unset to use default. |
| `trigger_webhook` | `bool` | Optional (default `True`) | Notifies the **legacy backend** that this patient's form was received — POSTs the raw input form (not the generated summary) to `TOOLS_URL` + `PRECONS_TOOL_TRIGGER_API`, fire-and-forget on a background thread, before any LLM work runs. See **Webhook Configuration** above. **Pass `False` for local/offline runs** or you'll get connection errors. |
| `mock` | `bool` | Optional (default `False`) | When `True`, skips all LLM calls and the webhook and returns a fixed dummy response. Use for integration testing without API keys. |
| `debug` | `bool` | Optional (default `False`) | Raise the module log level to `DEBUG` for this call (prompts, salience profile, scores). Otherwise logs at `WARNING`. |
| `output_style` | `str` | Optional (default `"paragraph"`) | Format of the two summaries: `"paragraph"` (dense prose) or `"markdown"` (grouped bullets). |
| `output_size` | `str` | Optional (default `"medium"`) | Detail level: `"small"` (only the most critical), `"medium"` (balanced), `"large"` (exhaustive), or `"all"` (returns a **list** of the small/medium/large variants). |

### Input schema (`client_details`)

Field annotations (read straight from the code in [salience.py](salience.py) and
[summarize.py](summarize.py)):

- **[required]** — a top-level key the code indexes directly; a missing key
  raises `ValueError` (via [validation.py](validation.py)). The list/object may
  still be **empty**, just present.
- **[optional]** — accessed with a fallback; safe to omit.
- **[ignored]** — present in the export but **not read** by this module
  (`meta`, `pre_consultation_session`). Every `*_id` field is an internal join
  key and is ignored — only the paired `*_label` is read.

```jsonc
{
  "meta": { ... },                       // [ignored]
  "pre_consultation_session": { ... },   // [ignored]
  "category_selections": [               // [optional] read for its category_label ONLY — becomes the profile's
                                          // second line ("Health categories the patient selected: ..."), which
                                          // is what the summary's opening statement of goals + categories draws from
    { "category_id": "heart_bp", "category_label": "Heart & Blood Pressure" }
  ],

  "patient_baseline": {                  // [required] object; must carry a non-empty "id"
    "id": "abce",                        //   [required] trace/client id — threaded into every Langfuse trace for per-client filtering/cost
    "first_name": "Priya",               //   [optional] webhook payload only (the profile stays identity-free)
    "last_name": "Sharma",               //   [optional] webhook payload only
    "contact_email": "priya@example.com",//   [optional] webhook payload only
    "date_of_birth": "1990-08-12",       //   [optional] ISO date; age is computed from it for demographic-anomaly checks
    "gender": "female"                   //   [optional] used for demographic-anomaly checks
  },

  "concerns": [                          // [required] (may be empty) — the descriptive material; becomes the "Reported concerns" section
    {
      "concern_label": "High Cholesterol",           // [required] the patient-declared concern
      "category_label": "Heart & Blood Pressure",    // [optional]
      "functional_impact_label": "Occasionally affects me", // [optional] how much it affects daily life
      "duration_impact_label": "More than 3 years",  // [optional] how long
      "progression_impact_label": "Gradually worsening", // [optional] trend
      "confidence_score": 77,            // [optional] 0-100; low scores seed a "confirm" checklist item
      "probe_flagged": true,             // [optional] flagged for validation
      "probe_question_count": 10,        // [optional] a flagged concern with 0 questions seeds a gap
      "probe_positive_count": 7,         // [optional]
      "symptoms": [                      // [optional] positive symptoms rendered inline
        { "symptom_label": "High BP reading" }
      ],
      "concern_sources": [               // [optional] how the patient knows (family, lab result, symptoms)
        { "source_label": "It runs in my family" }
      ],
      "family_history": [                // [optional] hereditary signal FOR THIS concern (tied to the patient's own condition)
        { "relation_label": "Mother", "age_band_label": "50–60" }
      ],
      "cluster_probe_answers": [         // [optional] validation Q&A; "yes" rendered inline, "no" folded into a compact "answered no to:" note
        { "probe_label": "BP ever found high?", "cluster_label": "Cardiometabolic Risk", "value": "yes" }
      ]
    }
  ],

  "medical_history": {                   // [required] object
    "medication_status": "medication_supplement", // [optional]
    "diagnoses": [                       // [optional] entries whose label is "None" are dropped
      { "diagnosis_label": "Hypertension (BP)", "is_reproductive": false }
    ],
    "medications": [                     // [optional] rendered name (dosage, frequency, duration)
      { "name": "Amlodipine", "dosage": "5mg", "frequency": "Once daily", "duration": "2 years" }
    ],
    "allergies": [                       // [optional] NEW in v3 — feeds the summary and a checklist seed
      { "name": "Sulfa drugs" }
    ],
    "surgeries": [ ... ],                // [optional] name (area, when, reason)
    "sexual_health_answers": [           // [optional] positives inline; meaningful "no" kept as a pertinent negative
      { "question_label": "Trying to conceive?", "option_id": "no", "option_label": "No" }
    ]
  },

  "lifestyle_answers": [                 // [required] (may be empty) — full lifestyle profile; pure-absence answers (e.g. tobacco: none) are dropped
    { "field_label": "Activity", "option_value": "light", "option_label": "Light" }
  ],

  "cluster_scores": [                    // [required] (may be empty) — the clusters; drives mode selection and the profile's "Health patterns" section
    {
      "cluster_label": "Metabolic Health",   // [required] shown in the profile under "Health patterns"
      "final_score": 70,                      // [required] 0-100; drives criticality banding (very_strong_pattern/strong_pattern/weak_signal)
      "bucket_id": "strong_pattern",          // [required] very_strong_pattern → HIGH, strong_pattern → MODERATE, weak_signal → LOW
      "bucket_label": "Strong Pattern",       // [optional] shown in the profile
      "lifestyle_signals_triggered": [        // [optional] rendered as the cluster's drivers
        { "signal_label": "DESK_JOB" }
      ],
      "family_risk_contribution": 2,          // [optional] >0 corroborates that family signal lifted this cluster
      "validation_skip_reason": "not_probed"  // [optional] a non-weak cluster left "not_probed" seeds a checklist gap
    }
  ],

  "health_goals": [                      // [required] (may be empty) — the summary opens by stating these
    { "goal_label": "Weight loss", "priority": 1 }
  ]
}
```

**Mode selection.** If any cluster's bucket is `strong_pattern` / `very_strong_pattern`
the patient is in **CONCERN** mode; otherwise **WELLNESS** mode. The mode chooses the
checklist axes (see `tag` below). Each checklist probe stands on its own — it is not
attributed to a specific cluster; `score` is `probability × tag_weight`, then an
intra-tag rank decay so one prolific axis can't bury another's best probe.

### Output schema

Each result is a JSON-serialisable dict carrying its own `output_style` /
`output_size` plus the three sections. **When `output_size="all"` the return is a
LIST** of three such dicts (one each for small / medium / large); the checklist is
identical across them.

```jsonc
{
  "output_style": "paragraph",
  "output_size": "medium",
  "preconsultation_summary": "Patient reports mid-day energy crashes ... Stated goals are weight loss, balancing hormones and improving energy ...",
  "quick_summary": "Mid-day energy crashes; prediabetes; maternal hypercholesterolemia at 50-60; goals of weight loss and better energy",
  "family_risk_summary": "Maternal hypercholesterolemia (mother aged 50–60), a hereditary signal toward the reported high cholesterol ...",
  "family_risk_present": true,
  "preconsultation_checklist": [
    {
      "probe": "Are current glycemic labs (A1c, fasting glucose) worth having on hand?",
      "tag": "missing_context",
      "score": 0.41,
      "reason": "'Prediabetes' was reported with low confidence and minimal daily impact; objective labs are needed to confirm status."
    }
  ]
}
```

- `quick_summary` — a short, natural but concise, **subjectless** line stating
  the facts (not the evidence), most critical first — the doctor's five-second
  glance. Capped at ~30 words; always one line regardless of
  `output_style`/`output_size`.
- `family_risk_present` — LLM-set boolean: `true` only when the family history
  holds a signal worth the doctor's attention. When `false`, `family_risk_summary`
  is an empty string (nothing noteworthy, or no family history at all).

All summaries are length-capped: preconsultation summary ~45/90/160 words
(small/medium/large), quick summary ~30 words, family-risk summary ~35 words,
each checklist probe ~20 words.

`tag` is one of (the mode decides which set applies):
- **Concern mode:** `red_flag_escalation`, `contradiction_resolution`,
  `factual_discrepancy`, `risk_refinement`, `treatment_efficacy`,
  `diagnostic_clarification`, `missing_context`, `medication_adherence`,
  `lifestyle_driver`.
- **Wellness mode:** `factual_discrepancy`, `preventive_screening`,
  `early_risk_surveillance`, `baseline_establishment`, `lifestyle_optimization`,
  `goal_alignment`.


## 2. Insight Extraction from Reports — `extract_insights` / `aextract_insights`

Use this when you have an **uploaded patient document** and want page-cited
clinical insights. Async variants (`aextract_insights`, `aextract_insights_batch`)
are native coroutines — use them when calling from an async context to avoid
the `asyncio.run` overhead that the sync wrappers incur internally.

```python
from intelligence_engine.preconsultation import extract_insights, aextract_insights

# Option A — pass the bytes directly
result = extract_insights(
    filebytestream=raw_bytes,
    filename="blood_panel.pdf",          # needed for type detection when no filepath
    metadata={"doc_id": "doc-1", "name": "Blood Panel", "upload_date": "2026-06-01", "owner": "PT-2001"},
    client_details={"client_id": "CL-001", "name": "Jane Doe", "age": 29, "gender": "Female"},
)

# Option B — let it read from disk (bytes omitted ⇒ read from filepath)
result = extract_insights(
    filepath="/path/to/blood_panel.pdf",
    metadata={...},
    client_details={...},
)
```

| Argument | Type | Required? | Notes |
| --- | --- | --- | --- |
| `filepath` | `str \| None` | **Conditionally required** (default `None`) | Path on disk. Byte source when `filebytestream` is omitted; type source when `filename` is omitted. At least one of `filepath`/`filebytestream` must be given. |
| `filebytestream` | `bytes \| None` | **Conditionally required** (default `None`) | Raw file bytes. **Takes precedence** over `filepath`. At least one of `filepath`/`filebytestream` must be given. |
| `metadata` | `dict` | **Required** | Must include a non-empty `doc_id` (raises `ValueError` otherwise). See full annotated schema below. |
| `client_details` | `dict` | **Required** | Must include a non-empty `client_id` (raises `ValueError` otherwise). Add `name` for PII redaction. See full annotated schema below. |
| `filename` | `str \| None` | Conditionally optional (default `None`) | Original filename, used **only** for type detection. Optional **if** `filepath` is given (basename is used); otherwise **required** so the file type is known. |
| `max_concurrency` | `int` | Optional (default `5`) | Cap on in-flight LLM/VLM calls. Leave as-is unless tuning throughput. |
| `ocr_config` | `OCRConfig` | Optional (default `DEFAULT_OCR_CONFIG`) | Leave as-is for normal use. Pass `LEGACY_OCR_CONFIG` only to reproduce the original OCR behaviour. |
| `strategy_name` | `str` | Optional (default `"default"`) | Label embedded in the Langfuse trace name/tags; only matters when comparing strategies. |
| `budget` | `float \| None` | Optional (default `None`) | Per-client USD budget for the run. Falls back to the `INSIGHT_EXTRACTION_BUDGET` env var; when neither is set, no budget gating is applied. See **Cost gating** below. |
| `mock` | `bool` | Optional (default `False`) | When `True`, skips file reading and all LLM calls and returns a dummy result. `doc_id`/`client_id` are still required and validated. |
| `debug` | `bool` | Optional (default `False`) | Raise the module log level to `DEBUG` for this call (per-page blocks, prompts, redaction, consolidation groups). Otherwise logs at `WARNING`. |

Minimum viable calls:

```python
# smallest valid metadata
metadata = {"doc_id": "doc-1"}

# smallest valid client_details (client_id required; age/gender for contradiction detection)
client_details = {"client_id": "CL-001", "name": "Jane Doe", "age": 29, "gender": "Female"}
```

Supported file types: `pdf`, `docx`, `jpg`, `jpeg`, `png`, `heic`, `heif`, `webp`, `txt`, `md`.
(`heic`/`heif`/`webp` are transcoded to JPEG internally before OCR.)

### Output schema (`ExtractionRunResult`)


```jsonc
{
  "results": [                       // processed documents (each a DocumentInsights)
    {
      "doc_id": "doc-1",             // name / upload_date / owner default to null (not populated by the pipeline)
      "title": "Comprehensive Metabolic Panel",  // short 2-6 word name for what the report IS (LLM-inferred; "" if none)
      "summary": "ALT elevated at 56 U/L (ref 7-40) and LDL 165 mg/dL above range; stable hypothyroidism on levothyroxine.",
                                     // one paragraph, most abnormal/critical findings first; stated directly (no "the report shows ..." phrasing)
      "contains_biomarkers": true,   // true if ANY biomarker measurement (in or out of range) was found
      "abnormal_biomarkers": [       // only the OUT-OF-RANGE ones
        {
          "name": "ALT",
          "value": "56",
          "unit": "U/L",             // null if the report prints none
          "reference_range": "7-40"  // as printed; null if the report prints none
        }
      ]
    }
  ],
  "skipped": [                       // documents not processed, with the reason
    {
      "doc_id": "doc-9",
      "filename": "huge_scan.pdf",
      "reason": "exceeds_token_limit",   // exceeds_token_limit | over_budget | extraction_failed
      "detail": "estimated 41200 input tokens exceeds limit 40000"
    }
  ]
}
```

Each processed document is a **prioritized summary paragraph** (abnormal/critical
findings first) plus **structured biomarker data**: `contains_biomarkers` flags
whether the report holds any biomarker measurement at all, and
`abnormal_biomarkers` lists the out-of-range ones with value, unit, and reference
range. (The pipeline no longer returns a per-insight list or citations.)

A document that raises during processing (corrupt file, unsupported type, an LLM
error that survives the client's retries) does **not** abort the batch: it is
isolated as a `skipped` entry with `reason: "extraction_failed"` and `detail`
carrying the underlying error, while every other document still returns.

### Cost gating (token limit + per-client budget)

Before any LLM/OCR calls, every input file is **pre-read cheaply** (native text
only, no OCR) to estimate its input tokens and cost (via the `cost` module):

1. **Per-file token limit** — a file whose estimated input tokens exceed the
   `INSIGHT_EXTRACTION_TOKEN_LIMIT` env var is skipped with reason
   `exceeds_token_limit`.
2. **Per-client budget** — surviving files are grouped by `client_id`. For each
   client, its current spend is fetched from Langfuse (by environment +
   `client_id`) and subtracted from the `budget` (arg, or `INSIGHT_EXTRACTION_BUDGET`
   env). Within the remaining budget the **cheapest files (by estimated input
   cost) are taken as a prefix** — the first file that does not fit and every
   file after it are skipped with reason `over_budget`. If neither `budget` arg
   nor env is set, budget gating is off.

Skipped files never reach the pipeline and appear only in `skipped`. If Langfuse
credentials are absent or the spend query fails, current spend is treated as
`0.0` (gating never blocks a run on infrastructure errors).

### Async usage

```python
from intelligence_engine.preconsultation import aextract_insights, aextract_insights_batch

# single document
result = await aextract_insights(filepath="report.pdf", metadata={...}, client_details={...})

# batch
results = await aextract_insights_batch([
    {"filepath": "a.pdf", "metadata": {...}, "client_details": {...}},
])
```

### Batch — `extract_insights_batch`

```python
results = extract_insights_batch([
    {"filepath": "a.pdf", "metadata": {...}, "client_details": {...}},
    {"filename": "b.png", "filebytestream": b"...", "metadata": {...}, "client_details": {...}},
])
```

Each report dict accepts the same fields as `extract_insights` (each needs a
`metadata.doc_id` and a `client_details.client_id`). `filename` is optional, and
`filebytestream` may be omitted to read from `filepath`. Returns an
`ExtractionRunResult` — `results` holds the processed documents, `skipped` lists
any dropped by cost gating (see **Cost gating** above). Concurrency is shared
across all processed documents and all their pages. Pass `budget=` (or set
`INSIGHT_EXTRACTION_BUDGET`) to enable per-client budget gating.

`mock=True` is also accepted as a top-level kwarg and applies to every report
in the batch — no files are read, no LLM calls are made, and each entry returns
a dummy `DocumentInsights` derived from its own `metadata` (with no skips).

---

## 3. Form-Exists Endpoint

A separate HTTP API (not a Python function in this module) that checks whether a
client has already submitted preconsultation data — useful before asking them to
fill out a new form.

**Endpoint:** `GET https://api.ai.biopeak.health/preconsultation/v1/form-exists`

**Authentication:** Bearer token in the `Authorization` header.

### Request

Query parameters:

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string (email) | **Yes** | Client's email |

### Response (JSON body)

| Field | Type | Description |
|---|---|---|
| `exists` | bool | Whether form data exists for this client |
| `source` | string \| null | `"typeform"`, `"onboarding"`, or `null` if `exists` is `false` |

### Example

```bash
curl -X GET "https://api.ai.biopeak.health/preconsultation/v1/form-exists?email=client@example.com" \
  -H "Authorization: Bearer <TOKEN>"
```

```json
{ "exists": true, "source": "typeform" }
```