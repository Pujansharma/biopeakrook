# Pre-Consultation API — v1

**Base:** `/pre-consultation/`

**Auth:** `Authorization: Bearer <access_token>`

**OpenAPI:** `/pre-consultation/openapi/` · Swagger UI `/pre-consultation/openapi/docs/`

**v2 flow:** [api-pre-consultation-v2.md](./api-pre-consultation-v2.md)

**Staff result API:** [api-pre-consultation-result.md](./api-pre-consultation-result.md)

**Test scenarios:** [simulation.md](./simulation.md)

### Flow

```
1  POST session/start
2  patient_baseline
3  patient_category
4  patient_concern
5  patient_symptom
6  patient_concern_probe
7  patient_medical_history_context
8  patient_lifestyle_environment     → next_layer: cluster_probe | goals_priorities
9  patient_cluster_probe             (conditional)
10 patient_goals_priorities
11 GET session/result
12 POST session/complete
```

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
| Complete | Step 12 sets `status = completed`; further layer PUTs → `409` |

**Cascade on deselect:** Removing a category removes its concerns and downstream answers. Removing a concern removes its symptoms, impact, and probes.

**Gender `other`:** Step 7 skips sex-gated reproductive + sexual-health catalogs. PUT rejects sexual-health payloads.

**Lifestyle rewind:** Re-PUT lifestyle clears prior cluster-probe answers, wipes scores, recalculates provisional-only, then sets `next_layer`.

---

## Step 1 — POST `/session/start/`

One session per user. Starts or resumes.

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

## Step 2 — `patient_baseline`

**Header:** `X-Customer-Profile-ID` optional (required to persist profile data)

### GET `/session/patient_baseline/`

| Field | Type | Notes |
|---|---|---|
| `first_name` | string | max 100 |
| `last_name` | string | max 100 |
| `dob` | date \| null | `YYYY-MM-DD` |
| `gender` | string \| null | `male`, `female`, `other` |
| `email_address` | string | |
| `address.line_1` | string | max 255 |
| `address.line_2` | string | max 255 |
| `address.city` | string | max 100 |
| `address.state` | string | max 100 |
| `address.pin_code` | string | max 20 |
| `address.residency_type` | string \| null | `home`, `office`, `other` |

### PUT `/session/patient_baseline/`

All fields required except `last_name`, `address.line_2` (default `""`). Advances `current_layer` to `patient_category`.

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |
| `409` | Session completed |
| `404` | No session / profile |

---

## Step 3 — `patient_category`

### GET `/session/patient_category/`

Returns full category catalog with `selected` flags.

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

## Step 4 — `patient_concern`

### GET `/session/patient_concern/`

Categories from step 3 only. Each has `concerns[]` with `id`, `label`, `selected`.

### PUT `/session/patient_concern/`

```json
{ "concern_ids": ["heart_bp_high_bp", "metabolism_blood_sugar"] }
```

| Validation |
|---|
| Each id valid in directive |
| Parent category must be selected in step 3 |

Advances `current_layer` to `patient_symptom`.

---

## Step 5 — `patient_symptom`

### GET `/session/patient_symptom/`

| Field | Notes |
|---|---|
| `concern_source`, `age_band`, `family_relation` | Directive catalogs |
| `concerns[]` | Per session concern: `id`, `label`, `selected_concern_source`, `selected_family_relation` (`relation_id`, `age_band_id`), `symptom[]` (`id`, `label`, `selected`) |

### PUT `/session/patient_symptom/`

```json
{
  "concerns": [
    {
      "id": "heart_bp_high_bp",
      "selected_symptom_ids": ["heart_bp_high_bp:high_bp_reading"],
      "selected_concern_source_ids": ["lab_result"],
      "selected_family_relations": []
    }
  ]
}
```

| Field | Notes |
|---|---|
| `selected_family_relations[].id` | PUT field name (`relation_id` on GET) |
| `lab_result` in sources | ↔ `selected_symptom_ids` non-empty |
| `family` in sources | ↔ `selected_family_relations` non-empty |

Advances `current_layer` to `patient_concern_probe`.

---

## Step 6 — `patient_concern_probe`

### GET `/session/patient_concern_probe/`

| Field | Notes |
|---|---|
| `functional_impact`, `duration_impact`, `progression_impact` | Directive catalogs |
| `concerns[]` | `id`, `label`, `selected_*_impact` (id or `""`), `category.label` |

### PUT `/session/patient_concern_probe/`

```json
{
  "concerns": [
    {
      "id": "heart_bp_high_bp",
      "selected_functional_impact_id": "regularly",
      "selected_duration_impact_id": "1_3yr",
      "selected_progression_impact_id": "stable"
    }
  ]
}
```

Advances `current_layer` to `patient_medical_history_context`.

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

| Field | Notes |
|---|---|
| `lifestyle_field[]` | `id`, `label`, `options[]` (`value`, `label`, `selected`) |
| `cluster_lifestyle`, `cluster_confidence` | Empty until first PUT |

### PUT `/session/patient_lifestyle_environment/`

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

On PUT: clears prior cluster-probe answers, wipes scores, recalculates, then returns `next_layer`.

```json
{
  "success": true,
  "data": { "next_layer": "patient_cluster_probe" }
}
```

| `next_layer` | Meaning |
|---|---|
| `patient_cluster_probe` | Go to step 9 |
| `patient_goals_priorities` | Skip step 9 |

---

## Step 9 — `patient_cluster_probe` *(conditional)*

Skip when step 8 `next_layer = patient_goals_priorities`.

### GET `/session/patient_cluster_probe/`

Concerns in flagged clusters only. Each has `cluster[]` with `cluster_probe[]` (`id`, `label`, `value`: `0`, `1`, or `null`).

### PUT `/session/patient_cluster_probe/`

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

Advances `current_layer` to `patient_goals_priorities`.

---

## Step 10 — `patient_goals_priorities`

### GET `/session/patient_goals_priorities/`

| Field | Notes |
|---|---|
| `max_health_goal_count` | Currently 3 |
| `health_goals[]` | `id`, `label`, `priority` (rank or `null`) |
| `previous_layer` | `patient_cluster_probe` or `patient_lifestyle_environment` |

### PUT `/session/patient_goals_priorities/`

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

Advances `current_layer` to `patient_health_map`.

---

## Step 11 — `patient_health_map`

### GET `/session/result/`

| Field | Type |
|---|---|
| `health_system` | `{ "label", "icon", "icon-class" }[]` |
| `cluster_count` | int |
| `concern_count` | int |
| `lifestyle_context` | `{ "label", "value" }[]` |
| `goals` | `{ "id", "label", "priority" }[]` |

---

## Step 12 — POST `/session/complete/`

No body. Requires `current_layer = patient_health_map`.

| Status | When |
|---|---|
| `200` | `{ "success": true, "data": { "status": "completed", "current_layer" } }` |
| `400` | Wrong layer |
| `409` | Already completed |
| `404` | No session |
