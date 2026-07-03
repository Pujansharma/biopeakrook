# Pre-consultation Intelligence Engine

Production-grade module for generating doctor-facing reference materials from structured patient intake data and clinical documents. Two independent capabilities work in tandem:

1. **Preconsultation Summary** — turns pre-consultation form data into clinical briefs, family risk assessments, and scored probe checklists
2. **Insight Extraction** — distills patient documents (PDFs, scans, reports) into page-cited, necessity-scored clinical findings

Both capabilities are production-hardened with:
- Automatic retry logic and timeout protection (90s per LLM call, 5 retries for transient failures)
- Comprehensive error classification and fail-soft patterns (extraction batches continue on per-document failure)
- Latency instrumentation ([timing.py](timing.py)) wired into application logs for oncall observability
- Error typing via `PreconsultationError` / `SummaryGenerationError` / `classify_retryable()` for fallback logic

See [errors.py](errors.py) and [timing.py](timing.py) for implementation details.

---

## Environment Variables

All environment variables are optional unless marked **[REQUIRED]**.

### LLM & API Credentials

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | string | (none) | OpenAI API key for ChatOpenAI (required for live LLM calls; omit for `mock=True` mode) |
| `LANGFUSE_PUBLIC_KEY` | string | (none) | Langfuse public key for trace logging |
| `LANGFUSE_SECRET_KEY` | string | (none) | Langfuse secret key for trace logging |
| `LANGFUSE_HOST` | string | `https://cloud.langfuse.com` | Langfuse server URL (or localhost for local tracing) |

### Webhook Configuration

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `TOOLS_URL` | string | `http://localhost:8000` | Base URL of the tool endpoint that receives summarize webhook payloads |
| `PRECONS_TOOL_TRIGGER_API` | string | `/preconsultation/v1/onboarding-webhook` | Endpoint path appended to `TOOLS_URL` for webhook POSTs |
| `ONBOARDING_WEBHOOK_SECRET` | string | (none) | HMAC-SHA256 signing secret for webhook payloads (optional; if set, all webhook POSTs are signed) |

**Example webhook flow:**
```bash
export TOOLS_URL="https://api.example.com"
export PRECONS_TOOL_TRIGGER_API="/webhooks/onboarding"
export ONBOARDING_WEBHOOK_SECRET="your-secret-key"

# Webhook is POSTed to: https://api.example.com/webhooks/onboarding
# Payload is signed with HMAC-SHA256 using the secret (see _post_webhook in summarize.py)
```

Webhook payloads include patient name, email, and the full summary output. Payloads are fire-and-forget on a daemon thread (do not block the summarize call). Failures are logged but do not fail the whole summarize operation.

### Insight Extraction Budgeting & Limits

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `INSIGHT_EXTRACTION_TOKEN_LIMIT` | int | `40000` | Max input tokens per document; larger documents are skipped with reason `exceeds_token_limit` |
| `INSIGHT_EXTRACTION_BUDGET` | float | (none) | Per-client USD budget for extraction runs; if set, docs are processed in order of estimated cost until budget is exhausted; remaining docs are skipped with reason `over_budget` |

### Prompt Versioning

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `ACTIVE_CHECKLIST_REGISTER` | string | `associate_v2` | Selects the checklist probe persona: `imperative_v1` (commanding) or `associate_v2` (deferential, "briefing the doctor") |

Available registers are defined in [prompts.py](prompts.py) under `_CHECKLIST_PROBE_REGISTERS`. Swap instantly without code deployment:
```bash
# Use the deferential "associate briefing doctor" tone
export ACTIVE_CHECKLIST_REGISTER=associate_v2

# Fall back to the original imperative tone
export ACTIVE_CHECKLIST_REGISTER=imperative_v1
```

---

## Mental model

- **Cluster** = a higher-level health pattern with criticality (final_score 0–100, bucket_id) and clinical drivers
- **Concern** = a patient-declared health concern within a cluster (e.g. *Sleep Onset Latency* within *Sleep & Recovery*)

## 1. Onboarding Summary — `summarize_patient` / `asummarize_patient`

Use this when you have a **structured pre-consultation form** and want the
doctor's pre-read. Both functions share the same signature and return the same
`PreconsultationSummaries` shape.

```python
from intelligence_engine.preconsultation import summarize_patient, asummarize_patient

# sync
summaries = summarize_patient(client_details, trigger_webhook=False)

# async (native coroutine — use inside an async context)
summaries = await asummarize_patient(client_details, trigger_webhook=False)
```

| Argument | Type | Required? | Notes |
| --- | --- | --- | --- |
| `client_details` | `dict` | **Required** | One pre-consultation form. Required top-level keys: `client_id`, `clusters`, `family_risk`, `medical_context`, `surgeries`, `patient_priorities`. Missing any of these (or a missing/empty `client_id`) raises `ValueError`. Optional: `metadata` object (`name`, `email_id` — used by the webhook), `age`, `gender`. See full annotated schema below. |
| `llm` | LangChain chat model | Optional (default `None`) | Leave unset to use the per-task config. When set, overrides model/config entirely. |
| `model` | `str` | Optional (default `None`) | Model name override (e.g. `"gpt-4o"`). Takes precedence over config but not over `llm`. Leave unset to use default. |
| `trigger_webhook` | `bool` | Optional (default `True`) | POSTs the result to the tool endpoint in a background thread. **Pass `False` for local/offline runs** or you'll get connection errors. |
| `mock` | `bool` | Optional (default `False`) | When `True`, skips all LLM calls and the webhook and returns a fixed dummy response. Use for integration testing without API keys. |

### Input schema (`client_details`)

Field annotations (read straight from the code in [salience.py](salience.py)):

- **[required]** — accessed directly; the call raises `KeyError` if the key is
  missing. A list/object key may still be **empty** (`[]` / `{}`), just present.
- **[optional]** — accessed with a fallback; safe to omit. Where it changes
  behaviour the default is given.
- **[required-if-present]** — the parent object is optional, but when you
  include it these keys must be there.
- **[ignored]** — part of the upstream form schema but **not read by this
  module**. Pass it or drop it; it has no effect on the output.


```jsonc
{
  "client_id": "CL-001",                 // [required] non-empty string; identifies the client. Threaded into every Langfuse trace's metadata for per-client filtering/cost.
  // [optional] identity fields. name/email_id used by the webhook trigger.
  "name": "Jane Doe", 
  "email_id": "jane@example.com",
  "age": 29,                             // [required] integer; used to detect age-inappropriate findings (e.g., pre-puberty pregnancy)
  "gender": "Female",                    // [required] string (e.g., "Male", "Female", "Other"); used to detect gender-inappropriate findings

  "clusters": [                          // [required] (may be an empty list)
    {
      "cluster_name": "Sleep & Recovery", // [required]
      "confidence": 85,                   // [required] 0-100;
      "priority": "Moderate",             // [optional] Critical|High|Moderate|Low; default Moderate(0.5).
      "review_status": "Needs Validation",// [optional] Needs Validation|Accept|Reject; "Needs Validation"/"Reject" seed the checklist
      "supporting_nodes": [               // [required] (may be empty)
        {
          "node_name": "Sleep Onset Latency", // [required]
          "confidence": 82,                    // [required] 0-100;
          "priority": "Moderate",              // [optional] default Moderate(0.5)
          "rationale": "Difficulty falling asleep within 30 min.", // [optional]
          "related_clusters": ["Sleep & Recovery", "Stress Axis"], // [optional]
          "related_family_history": [          // [optional] default []
            { "relative": "Father", "condition": "Type 2 Diabetes", "age": 45 } 
          ],
          "evidence": {                        // [optional] default {};
            "trend": "Worsening",              //   [optional] Worsening|Stable|Improving;
            "duration": "8 months",            //   [optional] 
            "impact": "Moderate impact on alertness" //   [optional]
          },
          "signals": ["Takes 45+ minutes to fall asleep"], // [optional] default [];
          "evidence_count": 5                  // [ignored]
        }
      ],
      "strength": "Moderate",             // [ignored]
      "evidence_count": 9,                // [ignored]
      "supporting_diagnoses": ["Pre-diabetes watch"],         // [optional]
      "family_history": [                                      // [optional]
        { "relative": "Father", "condition": "Type 2 Diabetes", "age": 45 }
      ],
      "lifestyle_factors": ["Late-night screen use"],         // [optional]
      "validation_responses": ["Feels groggy most mornings"], // [optional]
      "confidence_drivers": ["Wearable data consistency"],    // [optional]
      "notes": "Reviewer note: insulin conversation likely."   // [optional] free-text reviewer guidance;
    }
  ],

  "family_risk": {                        // [required] key (may be {} or null)
    "disease_burden": [                   // [optional] default []
      { "condition": "Type 2 Diabetes", "risk": "High", "affected_relatives": ["Father", "Brother"] }
    ],
    "cluster_contributions": [            // [optional] default []
      { "cluster_name": "Metabolic Health", "contribution": "Strong paternal diabetes line" }
    ]
  },

  "medical_context": {                    // [required]
    "diagnoses": [],                      //   [required] (may be empty)
    "medications": []                     //   [optional] default []
  },

  "surgeries": [                          // [required] key (may be empty)
    { "procedure": "Appendectomy", "current_impact": "Low" } // current_impact: Significant|Moderate|Low
  ],

  "patient_priorities": ["Improve sleep onset and quality"] // [required] key (may be empty)
}
```

### Output schema (`PreconsultationSummaries`)

```jsonc
{
  "preconsultation_summary": "29-year-old female with worsening sleep onset ...",
  "family_risk_summary": "Strong paternal diabetes line, cross-referenced ...",
  "preconsultation_checklist": [
    {
      "probe": "Validate metabolic drivers of poor recovery",
      "tag": "diagnostic_clarification",
      "score": 0.74,
      "node_name": "Sleep Onset Latency",
      "reason": "Sleep and stress nodes co-occur; metabolic link warrants probing."
    }
  ]
}
```

`tag` is one of:
- **Concern mode:** `red_flag_escalation`, `contradiction_resolution`,
  `risk_refinement`, `treatment_efficacy`, `diagnostic_clarification`,
  `missing_context`, `medication_adherence`, `lifestyle_driver`.
- **Wellness mode:** `preventive_screening`, `early_risk_surveillance`,
  `baseline_establishment`, `lifestyle_optimization`, `goal_alignment`.


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

Minimum viable calls:

```python
# smallest valid metadata
metadata = {"doc_id": "doc-1"}

# smallest valid client_details (client_id required; age/gender for contradiction detection)
client_details = {"client_id": "CL-001", "name": "Jane Doe", "age": 29, "gender": "Female"}
```

Supported file types: `pdf`, `docx`, `jpg`, `jpeg`, `png`, `txt`, `md`.

### Output schema (`ExtractionRunResult`)

> **Breaking change:** both `extract_insights` and `extract_insights_batch` (and
> their async variants) now return an **`ExtractionRunResult`** wrapping the
> processed documents plus any that were skipped by cost gating — not a bare
> `DocumentInsights` / `list[DocumentInsights]`. For a single-document call,
> `results` holds 0 or 1 entries.

```jsonc
{
  "results": [                       // processed documents (each a DocumentInsights)
    {
      "doc_id": "doc-1",
      "insights": [
        {
          "id": "doc-1-g0",
          "title": "Elevated ALT",
          "category": "abnormal_measurement", // abnormal_measurement | symptom | clinical_finding | imaging_finding | diagnosis | medication | procedure | treatment_recommendation | monitoring_plan | risk_factor
          "necessity": 82,                   // 1-100: how necessary for the doctor to see pre-consult.
          "index": { "page": 4, "bbox": [72.0, 310.5, 540.0, 330.0] },  // bbox may be null
          "content": "ALT elevated at 56 U/L (normal 7-40).",  // stated directly — no "the report shows ..." phrasing
          "citations": [
            {
              "fact": "ALT 56 U/L (normal 7-40)",
              "page": 4,
              "bbox": [72.0, 310.5, 540.0, 330.0],   // may be null
              "citation": "ALT 56 U/L (normal 7-40) <Page 4>"
            }
          ]
        }
      ]
    }
  ],
  "skipped": [                       // documents not processed, with the reason
    {
      "doc_id": "doc-9",
      "filename": "huge_scan.pdf",
      "reason": "exceeds_token_limit",   // exceeds_token_limit | over_budget
      "detail": "estimated 41200 input tokens exceeds limit 40000"
    }
  ]
}
```

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

## 3. Form-Exists Endpoint — `GET /preconsultation/v1/form-exists`

Check whether a client has already submitted preconsultation data (e.g., via Typeform).
This is useful before requesting a new form submission to avoid duplication.

**Endpoint:** `GET /preconsultation/v1/form-exists`

**Authentication:** Bearer token (set via API gateway configuration)

### Request

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `email` | string (email) | **Yes** | Client's email address |

### Response

HTTP 200 with JSON body:

```json
{
  "exists": true,
  "source": "typeform"
}
```

| Field | Type | Values | Description |
|---|---|---|---|
| `exists` | bool | `true` \| `false` | Whether preconsultation data exists for this client |
| `source` | string \| null | `"typeform"` \| `"onboarding"` \| `null` | Data source (`typeform` for Typeform submissions, `onboarding` for API-submitted forms, `null` if `exists` is `false`) |

### Examples

**Request — form exists (Typeform source):**
```bash
curl -X GET "https://api.example.com/preconsultation/v1/form-exists?email=alice@example.com" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "exists": true,
  "source": "typeform"
}
```

**Request — form does not exist:**
```bash
curl -X GET "https://api.example.com/preconsultation/v1/form-exists?email=bob@example.com" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "exists": false,
  "source": null
}
```

### Error Responses

| Status | Body | Reason |
|---|---|---|
| `400` | `{"error": "email is required"}` | Missing `email` query parameter |
| `400` | `{"error": "invalid email format"}` | Malformed email address |
| `401` | `{"error": "Unauthorized"}` | Missing or invalid Bearer token |
| `500` | `{"error": "Internal server error"}` | Unexpected backend failure |

---

## Error Handling & Resilience

### Exception Types

All exceptions inherit from `PreconsultationError` (see [errors.py](errors.py)):

- **`SummaryGenerationError`** — raised when `summarize_patient` fails at any stage
  - Attributes: `stage` (which step failed), `client_id`, `retryable` (bool), `cause` (original exception)
  - Classify with `classify_retryable(exc)` to decide whether to retry or escalate

- **`classify_retryable(exc: Exception) -> bool`**
  - Returns `True` for transient failures: rate limits (429), timeouts, upstream 5xx
  - Returns `False` for terminal failures: auth errors, insufficient quota, context length exceeded, parse errors
  - Matches exception type names via MRO, so it works without tight SDK imports

### Fail Patterns

**Summarize (fail-whole):** If any step (summaries, checklist, webhook) fails terminally, the whole `summarize_patient` call raises `SummaryGenerationError` with `retryable=False`. The form is atomic — either all three summaries are produced or none.

**Extract (fail-soft):** If a document fails to process (OCR error, cost-gating, LLM failure), it is skipped (added to `skipped` with reason + detail) and the batch continues. The batch result includes both processed documents (`results`) and skipped ones (`skipped`). Batch resilience is controlled by `return_exceptions=True` internally.

### Timeout & Retry Configuration

All LLM calls are configured with:
- **Timeout:** 90 seconds per request (transient timeouts are retried)
- **Max retries:** 5 attempts with exponential backoff (via ChatOpenAI client-side)

Override per task in [llm_config.py](llm_config.py) TASK_CONFIGS without touching call sites:
```python
TASK_CONFIGS["my_task"] = TaskLLMConfig(
    model="gpt-5-mini",
    timeout=120.0,  # 2 minutes for this task
    max_retries=3,   # fewer retries for time-sensitive work
)
```

### Latency Instrumentation

Every LLM stage and batch operation logs its elapsed time at INFO level (SUCCESS) or WARNING level (FAILURE, re-raises):

```python
from intelligence_engine.preconsultation.timing import log_stage

with log_stage("stage_name", client_id="CL-001", doc_id="doc-5"):
    # LLM call here
    result = await llm.ainvoke(...)
```

Logs appear as structured entries:
```
[timing] stage=stage_name client_id=CL-001 doc_id=doc-5 elapsed_ms=1234.5
```

Integrate into your observability stack (ELK, DataDog, CloudWatch) by grepping for `[timing]` lines. No Langfuse dependency required for timing — it works standalone.