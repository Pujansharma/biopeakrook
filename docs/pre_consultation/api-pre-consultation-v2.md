# Pre-Consultation API — v2

**Base:** `/pre-consultation/`

**Auth:** `Authorization: Bearer <access_token>`

**OpenAPI:** `/pre-consultation/openapi/` · Swagger UI `/pre-consultation/openapi/docs/`

**v1 flow:** [api-pre-consultation-v1.md](./api-pre-consultation-v1.md) — original routes stay unchanged.

**Staff result API:** [api-pre-consultation-result.md](./api-pre-consultation-result.md)

**Test scenarios:** [simulation.md](./simulation.md)

## Flow

Remixes order and merges symptom into concern probe. Shared layers keep v1 GET paths where payloads match.

```text
1  POST session/start
2  patient_baseline/v2               → current_layer: goals_priorities
3  patient_goals_priorities/v2       → current_layer: patient_category
4  patient_category                  (v1)
5  GET patient_concern (v1)
   PUT patient_concern/v2            → current_layer: patient_concern_probe
6  patient_concern_probe/v2          (merged symptom + probe)
                                     → current_layer: medical_history_context
7  patient_medical_history_context   (v1)
8  GET patient_lifestyle_environment (v1 — same payload)
   PUT patient_lifestyle_environment/v2
                                     → next_layer: cluster_probe | health_map
9  GET patient_cluster_probe (v1)
   PUT patient_cluster_probe/v2      → current_layer: patient_health_map
                                     (conditional; skip when next_layer = health_map)
10 GET session/result/v2             (+ previous_layer)
11 POST session/complete
```

| v2-only / branched endpoint | Diff vs v1 |
|---|---|
| `patient_baseline/v2` | Height/weight optional (cm/kg); address optional; PUT → `patient_goals_priorities` |
| `patient_goals_priorities/v2` | GET omits `previous_layer`; PUT → `patient_category` |
| `PUT patient_concern/v2` | Same body as v1; PUT → `patient_concern_probe` (skip symptom) |
| `patient_concern_probe/v2` | Merged symptom + probe GET/PUT; PUT → `patient_medical_history_context` |
| `PUT patient_lifestyle_environment/v2` | Same body/scoring; skip → `patient_health_map` (v1 skip → `goals_priorities`) |
| `PUT patient_cluster_probe/v2` | Same body as v1; PUT → `patient_health_map` (v1 → `goals_priorities`) |
| `session/result/v2` | Same result payload + `previous_layer` |

No GET `/v2/` for lifestyle or cluster_probe — use v1 GET (identical response).

Steps: `GET` load → `PUT` save. Most PUTs return `{ "success": true }`. Lifestyle PUT returns `{ "success": true, "data": { "next_layer" } }`. Medical history: optional `POST` file upload before `PUT`. Result when `current_layer` = `patient_health_map`.

---

## Global rules

| Rule | Detail |
|---|---|
| No session | `404` |
| PUT on completed session | `409` with `{ "success": false, "data": { "status": "completed", "current_layer" } }` |
| Throttle | GET 120/min · PUT/POST 30/min → `429` |
| Layer GET | `200` even when session completed |
| Layer PUT | Always advances `current_layer` to next step (including backtrack re-save) |
| Complete | Final step sets `status = completed`; further layer PUTs → `409` |

**Cascade on deselect:** Removing a category removes its concerns and downstream answers. Removing a concern removes its symptoms, impact, and probes.

**Gender `other`:** Medical history skips sex-gated reproductive + sexual-health catalogs. PUT rejects sexual-health payloads.

**Lifestyle rewind:** Re-PUT lifestyle/v2 clears prior cluster-probe answers, wipes scores, recalculates provisional-only, then sets `next_layer`. Always GET cluster_probe after lifestyle before PUT if routed there.

---

## Step 1 — POST `/session/start/`

Same as v1. One session per user. Starts or resumes.

### Request

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `interface` | string | Yes | `mobile`, `web` |
| `app_version` | string | Yes | max 50 |
| `locale` | string | Yes | max 20 |
| `device` | string | Yes | max 255 |

```json
{
  "interface": "mobile",
  "app_version": "1.0.0",
  "locale": "en-IN",
  "device": "iPhone 15 Pro"
}
```

### Response

| Status | When |
|---|---|
| `201` | New session |
| `200` | Resume in-progress |
| `409` | Already completed |
| `400` | Validation error |

```json
{
  "success": true,
  "data": {
    "status": "inprogress",
    "current_layer": "patient_baseline"
  }
}
```

---

## Step 2 — `patient_baseline/v2`

**Header:** `X-Customer-Profile-ID` optional (required to persist profile data)

### GET `/session/patient_baseline/v2/`

Demographics + height/weight (cm / kg). Address optional on response. No emergency contact.

| Field | Type | Notes |
|---|---|---|
| `first_name` | string | max 100 |
| `last_name` | string | max 100 |
| `dob` | date \| null | `YYYY-MM-DD` |
| `gender` | string \| null | `male`, `female`, `other` |
| `email_address` | string | |
| `height` | number \| null | centimeters |
| `weight` | number \| null | kilograms |
| `address` | object | may be empty |

### PUT `/session/patient_baseline/v2/`

All fields required except `last_name` (default `""`), `address` (optional), and `height` / `weight` (optional). Units fixed: `height` = cm, `weight` = kg. Omit → keep stored value; `null` → clear. Persists to `CustomerProfile.height_cm` / `weight_kg`. Advances `current_layer` to `patient_goals_priorities`.

| Field | Type | Constraints |
|---|---|---|
| `height` | number \| null | optional; 30–300 cm when set; omit keeps; `null` clears |
| `weight` | number \| null | optional; 1–500 kg when set; omit keeps; `null` clears |

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |
| `409` | Session completed |
| `404` | No session / profile |

---

## Step 3 — `patient_goals_priorities/v2`

Runs early in v2 (after baseline), before category.

### GET `/session/patient_goals_priorities/v2/`

Same as v1 goals GET minus `previous_layer`.

| Field | Notes |
|---|---|
| `max_health_goal_count` | Currently 3 |
| `health_goals[]` | `id`, `label`, `priority` (rank or `null`) |

### PUT `/session/patient_goals_priorities/v2/`

**Top-level JSON array** (not wrapped in `{ }`).

```json
[
  { "id": "weight_loss", "priority": 1 },
  { "id": "balance_hormones", "priority": 2 },
  { "id": "improve_energy", "priority": 3 }
]
```

| Validation |
|---|
| 1 to `max_health_goal_count` entries |
| Unique ids; priorities exactly `1`..`N` (no gaps) |

Advances `current_layer` to `patient_category`.

---

## Step 4 — `patient_category`

### GET `/session/patient_category/`

| Field | Type |
|---|---|
| `categories[].id` | string |
| `categories[].label` | string |
| `categories[].hint` | string |
| `categories[].icon` | string |
| `categories[].icon_class` | string |
| `categories[].selected` | boolean |

### PUT `/session/patient_category/`

```json
{ "category_ids": ["heart_bp", "metabolism"] }
```

| Field | Constraints |
|---|---|
| `category_ids` | string[]; may be `[]`; duplicates deduped; each id must exist in directive |

Advances `current_layer` to `patient_concern`.

---

## Step 5 — `patient_concern`

### GET `/session/patient_concern/`

Categories from step 4 only. Each has `concerns[]` with `id`, `label`, `selected`.

### PUT `/session/patient_concern/v2/`

Same body as v1. Advances `current_layer` to `patient_concern_probe` (skips `patient_symptom`).

```json
{ "concern_ids": ["heart_bp_high_bp", "metabolism_blood_sugar"] }
```

| Validation |
|---|
| Each id valid in directive |
| Parent category must be selected |

---

## Step 6 — `patient_concern_probe/v2`

Merged `patient_symptom` + `patient_concern_probe`.

### GET `/session/patient_concern_probe/v2/`

| Field | Notes |
|---|---|
| `concern_source`, `age_band`, `family_relation` | From symptom |
| `functional_impact`, `duration_impact`, `progression_impact` | From concern probe |
| `concerns[]` | Merged per concern: symptom fields + `selected_*_impact` + `category` |

### PUT `/session/patient_concern_probe/v2/`

Merged request fields per concern (symptom + probe). Advances `current_layer` to `patient_medical_history_context`.

```json
{
  "concerns": [
    {
      "id": "heart_bp_high_bp",
      "selected_symptom_ids": ["heart_bp_high_bp:high_bp_reading"],
      "selected_concern_source_ids": ["lab_result"],
      "selected_family_relations": [],
      "selected_functional_impact_id": "regularly",
      "selected_duration_impact_id": "1_3yr",
      "selected_progression_impact_id": "stable"
    }
  ]
}
```

| Field | Notes |
|---|---|
| `selected_family_relations[].id` | PUT field name (`relation_id` on GET) |
| `lab_result` in sources | ↔ `selected_symptom_ids` non-empty |
| `family` in sources | ↔ `selected_family_relations` non-empty |

---

## Step 7 — `patient_medical_history_context`

**Header:** `X-Customer-Profile-ID` optional (gates reproductive + sexual-health catalogs)

### GET `/session/patient_medical_history_context/`

| Field | Notes |
|---|---|
| `diagnosis`, `reproductive_diagnosis` | `{ "id", "label", "selected" }` |
| `allergies` | string[] |
| `surgeries` | `{ "name", "performed_when", "reason" }` |
| `medication_status` | `no`, `medication`, `supplements`, `medication_supplement`; `""` if unset |
| `medication` | `{ "name", "dosage", "frequency", "duration" }` |
| `sexual_health_question` | Gender/age-gated; `options[]` with `selected` |
| `medical_reports` | Uploaded files (see POST) |

### POST `/session/patient_medical_history_context/`

**Content-Type:** `multipart/form-data` · field `file`

| Rule | Value |
|---|---|
| Max per session | 10 |
| Max size | 10 MB |
| Allowed | PDF, JPEG, PNG, HEIC/HEIF, WebP |
| Layer gate | `current_layer = patient_medical_history_context` |

Response `data`: `id` (uuid), `filename`, `content_type`, `size_bytes`, `url`, `uploaded_at`

### PUT `/session/patient_medical_history_context/`

| Field | Constraints |
|---|---|
| `selected_diagnosis_ids` | `none` exclusive |
| `reproductive_diagnosis_ids` | Gender-valid; may be `[]` |
| `allergies` | max 255 per entry |
| `medication_status` | `no` → empty `medications`; else ≥1 entry |
| `medications[]` | `name`, `dosage`, `frequency`, `duration` |
| `surgeries[]` | `name`, `performed_when`, `reason` |
| `sexual_health_question[]` | `{ "id", "option_id" }`; `other` gender → `[]` |
| `medical_report_ids` | uuid[]; max 10; must exist on session; omitted ids deleted |

Advances `current_layer` to `patient_lifestyle_environment`.

---

## Step 8 — `patient_lifestyle_environment`

### GET `/session/patient_lifestyle_environment/`

Use **v1 GET** (no `/v2/` GET). Same payload.

| Field | Notes |
|---|---|
| `lifestyle_field[]` | `id`, `label`, `options[]` (`value`, `label`, `selected`) |
| `cluster_lifestyle`, `cluster_confidence` | Empty until first PUT |

### PUT `/session/patient_lifestyle_environment/v2/`

Same body and scoring as v1 PUT. Clears prior cluster-probe answers, wipes scores, recalculates provisional-only, then returns `next_layer`.

Flat JSON — **all** directive `lifestyle_field` ids required as keys.

| Key | Example values |
|---|---|
| `sleep_duration` | `<5 hrs`, `5-6 hrs`, `6-7 hrs`, `7-8 hrs`, `8+ hrs` |
| `eating_pattern` | `home_cooked_veg`, `mixed`, `eating_out`, `high_sweets`, `irregular_meals`, `restrictive_diet` |
| `sugary_drinks` | `rarely`, `sometimes`, `daily` |
| `activity_level` | `sedentary`, `light`, `moderate`, `active`, `very_active` |
| `desk_job` | `yes`, `no` |
| `stress_level` | `low`, `mild`, `moderate`, `high`, `very_high` |
| `hydration` | `lt_1L`, `1-2L`, `2-3L`, `3L_plus` |
| `alcohol` | `none`, `occasional`, `frequent` |
| `tobacco` | `none`, `smoked`, `smokeless`, `both`, `former` |

```json
{
  "success": true,
  "data": { "next_layer": "patient_cluster_probe" }
}
```

| `next_layer` | Meaning |
|---|---|
| `patient_cluster_probe` | Go to step 9 |
| `patient_health_map` | Skip cluster probe → result |

---

## Step 9 — `patient_cluster_probe` *(conditional)*

Skip when step 8 `next_layer = patient_health_map`.

### GET `/session/patient_cluster_probe/`

Use **v1 GET** (no `/v2/` GET). Concerns in flagged clusters only. Each has `cluster[]` with `cluster_probe[]` (`id`, `label`, `value`: `0`, `1`, or `null`).

### PUT `/session/patient_cluster_probe/v2/`

Same body/validation as v1. Advances `current_layer` to `patient_health_map` (v1 advances to `patient_goals_priorities`).

```json
{
  "concerns": [
    {
      "id": "heart_bp_high_cholesterol",
      "cluster_probe": [
        { "id": "cardiometabolic_risk_breathless_climbing_stairs", "value": "no" }
      ]
    }
  ]
}
```

| Validation |
|---|
| Concern id must be eligible (flagged cluster ∩ session concerns) |
| All probe ids for concern required (no missing/extra) |
| `value`: `yes`/`no`/`1`/`0`/`true`/`false` |

---

## Step 10 — `patient_health_map`

### GET `/session/result/v2/`

Same fields as GET `/session/result/`, plus `previous_layer`.

| Field | Type / Notes |
|---|---|
| `health_system` | `{ "label", "icon", "icon-class" }[]` |
| `cluster_count` | int |
| `concern_count` | int |
| `lifestyle_context` | `{ "label", "value" }[]` |
| `goals` | `{ "id", "label", "priority" }[]` |
| `previous_layer` | `patient_cluster_probe` or `patient_lifestyle_environment` |

---

## Step 11 — POST `/session/complete/`

No body. Requires `current_layer = patient_health_map`.

| Status | When |
|---|---|
| `200` | `{ "success": true, "data": { "status": "completed", "current_layer" } }` |
| `400` | Wrong layer |
| `409` | Already completed |
| `404` | No session |
