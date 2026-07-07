# Pre-Consultation API

**Base:** `/pre-consultation/`

**Auth:** `Authorization: Bearer <access_token>`

**OpenAPI:** `/pre-consultation/openapi/` · Swagger UI `/pre-consultation/openapi/docs/`

**Flow:**

```
1  POST session/start
2  patient_baseline
3  patient_category
4  patient_concern
5  patient_symptom
6  patient_concern_probe
7  patient_medical_history_context
8  patient_lifestyle_environment
9  patient_cluster_probe          (conditional)
10 patient_goals_priorities
11 patient_health_map              GET session/result
12 POST session/complete
```

Steps 2–10: `GET` load → `PUT` save. Step 7: optional `POST` file upload(s) before `PUT`. Step 11: health map UI loads via `GET /session/result/` (`current_layer` = `patient_health_map`).

---

## Global rules

**Status codes (layers):** `404` no session · PUT `409` session completed · `429` throttled (GET 120/min, PUT/POST 30/min)

### Session rules

- Layer GET returns `200` even when session completed.
- Layer PUT returns `409` when `status = completed`:

```json
{
  "success": false,
  "data": {
    "status": "completed",
    "current_layer": "patient_health_map"
  }
}
```

- Layer PUT advances `current_layer` only when session is already on that layer (see per-step side effects).
- Step 12 sets `status = completed`, `completed_at = now`. Further layer PUTs → `409`.

### Cascade reset on PUT

When PUT data **changed** (`has_changed`), downstream layers wiped in `transaction.atomic()` before persist.

| Layer saved (changed) | Downstream reset |
|---|---|
| `patient_category` | `patient_concern`, `patient_symptom`, `patient_concern_probe`, `patient_cluster_probe` |
| `patient_concern` | `patient_symptom`, `patient_concern_probe`, `patient_cluster_probe` |
| `patient_symptom` | `patient_concern_probe`, `patient_cluster_probe` |
| `patient_concern_probe` | `patient_cluster_probe` |
| `patient_medical_history_context` | `patient_cluster_probe` |
| `patient_lifestyle_environment` | `patient_cluster_probe` |

| Reset handler | Data cleared |
|---|---|
| `patient_category` | Category selections |
| `patient_concern` | All concerns (+ symptoms/sources/family history via FK cascade) |
| `patient_symptom` | Symptoms, sources, family history on existing concerns |
| `patient_concern_probe` | Impact ids, `confidence_score`, `probe_flagged` on concerns |
| `patient_cluster_probe` | Cluster probe answers; `probe_question_count`, `probe_positive_count`; cluster scores |

Cluster scores (`PreConsultationSessionClusterScore`) deleted on concern-chain resets and lifestyle reset.

Steps 7–10 do not cascade-reset other layers (except `patient_medical_history_context` and `patient_lifestyle_environment` clear cluster_probe when changed).

**Step 2:** gender or DOB change clears reproductive diagnoses + sexual-health answers (not allergies, surgeries, medications, medical reports).

**Step 7:** omitted `medical_report_ids` on PUT deletes report row + storage file.

---

## Step 1 — POST `/session/start/`

Starts or resumes session. One session per user.

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

| Status | When | Body |
|---|---|---|
| `201` | New session | `{ "success": true, "data": { "status", "current_layer" } }` |
| `200` | Resume in-progress | same |
| `409` | Already completed | `{ "success": false, "data": { "status": "completed", "current_layer" } }` |
| `400` | Validation error | `{ "detail": ... }` |

```json
{
  "success": true,
  "data": {
    "status": "inprogress",
    "current_layer": "patient_baseline"
  }
}
```

### Side effects

- `201`: creates session, `current_layer = patient_baseline`, `status = inprogress`.
- `200`: updates `interface`, `app_version`, `locale`, `device` only.

---

## Step 2 — `patient_baseline`

Persists to `CustomerProfile`, `CustomerProfileAddress`, `Customer.contact_email`.

### GET `/session/patient_baseline/`

**Headers:** `X-Customer-Profile-ID` optional

| Status | When |
|---|---|
| `200` | Always (empty strings/nulls if no profile) |
| `404` | No session |

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `first_name` | string | max 100; empty if unset |
| `last_name` | string | max 100; empty if unset |
| `dob` | date \| null | `YYYY-MM-DD` |
| `gender` | string \| null | `male`, `female` |
| `email_address` | string | from `Customer.contact_email` |
| `emergency_contact_name` | string | max 100 |
| `emergency_contact_phone` | string | E.164 |
| `address.line_1` | string | max 255 |
| `address.line_2` | string | max 255; may be empty |
| `address.city` | string | max 100 |
| `address.state` | string | max 100 |
| `address.pin_code` | string | max 20 |
| `address.residency_type` | string \| null | `home`, `office`, `other` |

```json
{
  "success": true,
  "data": {
    "first_name": "Priya",
    "last_name": "Sharma",
    "dob": "1990-08-12",
    "gender": "female",
    "email_address": "priya@example.com",
    "emergency_contact_name": "Raj Sharma",
    "emergency_contact_phone": "+919876543210",
    "address": {
      "line_1": "42 Linking Road",
      "line_2": "Bandra West",
      "city": "Mumbai",
      "state": "Maharashtra",
      "pin_code": "400050",
      "residency_type": "home"
    }
  }
}
```

### PUT `/session/patient_baseline/`

**Headers:** `X-Customer-Profile-ID` optional (required in practice for persist)

#### Request body

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `first_name` | string | Yes | max 100 |
| `last_name` | string | No | max 100; default `""` |
| `dob` | date | Yes | `YYYY-MM-DD` |
| `gender` | string | Yes | `male`, `female` |
| `email_address` | string | Yes | valid email |
| `emergency_contact_name` | string | Yes | max 100 |
| `emergency_contact_phone` | string | Yes |
| `address.line_1` | string | Yes | max 255 |
| `address.line_2` | string | No | max 255; default `""` |
| `address.city` | string | Yes | max 100 |
| `address.state` | string | Yes | max 100 |
| `address.pin_code` | string | Yes | max 20 |
| `address.residency_type` | string | Yes | `home`, `office`, `other` |

```json
{
  "first_name": "Priya",
  "last_name": "Sharma",
  "dob": "1990-08-12",
  "gender": "female",
  "email_address": "priya@example.com",
  "emergency_contact_name": "Raj Sharma",
  "emergency_contact_phone": "+919876543210",
  "address": {
    "line_1": "42 Linking Road",
    "line_2": "Bandra West",
    "city": "Mumbai",
    "state": "Maharashtra",
    "pin_code": "400050",
    "residency_type": "home"
  }
}
```

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |
| `409` | Session completed |
| `400` | Validation error |
| `404` | No session / profile |

#### Side effects

- `current_layer` → `patient_category` when session on `patient_baseline`.
- Gender or DOB change → deletes reproductive diagnoses + sexual-health answers on medical history.
- Upserts default `CustomerProfileAddress` (`country = India`, `is_default = true`).
- `has_changed` for cascade: gender or DOB only (baseline has no downstream cascade table entries).

---

## Step 3 — `patient_category`

### GET `/session/patient_category/`

| Status | When |
|---|---|
| `200` | Full directive category catalog with `selected` flags |
| `404` | No session |

#### Response `data.categories[]`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Directive category id |
| `label` | string | |
| `hint` | string | |
| `icon` | string | |
| `icon_class` | string | from directive `icon-class` |
| `selected` | boolean | Saved for this session |

```json
{
  "success": true,
  "data": {
    "categories": [
      {
        "id": "heart_bp",
        "label": "Heart & Blood Pressure",
        "hint": "BP, cholesterol, palpitations",
        "icon": "...",
        "icon_class": "...",
        "selected": true
      }
    ]
  }
}
```

### PUT `/session/patient_category/`

#### Request body

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `category_ids` | string[] | Yes | Directive ids; may be `[]`; duplicates deduped |

```json
{ "category_ids": ["heart_bp", "metabolism"] }
```

**Validation:** each id must exist in directive `category[]`.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |
| `409` | Session completed |

#### Side effects

- Syncs `PreConsultationCategorySelection` to submitted ids (removes unlisted).
- `current_layer` → `patient_concern` when on `patient_category`.
- Changed `category_ids` → cascade reset concern chain (steps 4–7 data).

---

## Step 4 — `patient_concern`

### GET `/session/patient_concern/`

Returns categories selected in step 3 only.

#### Response `data.categories[]`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Category id |
| `label` | string | |
| `icon` | string | |
| `icon_class` | string | |
| `concerns` | array | |
| `concerns[].id` | string | Concern id |
| `concerns[].label` | string | |
| `concerns[].selected` | boolean | |

```json
{
  "success": true,
  "data": {
    "categories": [
      {
        "id": "heart_bp",
        "label": "Heart & Blood Pressure",
        "icon": "...",
        "icon_class": "...",
        "concerns": [
          { "id": "heart_bp_high_bp", "label": "High Blood Pressure (BP)", "selected": true }
        ]
      }
    ]
  }
}
```

### PUT `/session/patient_concern/`

#### Request body

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `concern_ids` | string[] | Yes | Directive concern ids; may be `[]`; duplicates deduped |

```json
{ "concern_ids": ["heart_bp_high_bp", "metabolism_blood_sugar"] }
```

**Validation:**

- Each id valid in directive.
- Each concern's parent category must be in session `category_ids`.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Syncs `PreConsultationConcern` rows (removes unlisted concerns).
- `current_layer` → `patient_symptom` when on `patient_concern`.
- Changed data → cascade reset steps 5–7.

---

## Step 5 — `patient_symptom`

### GET `/session/patient_symptom/`

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `concern_source` | object[] | Directive catalog (`id`, `label`, …) |
| `age_band` | object[] | Directive catalog |
| `family_relation` | object[] | Directive catalog |
| `concerns` | array | One entry per session concern |
| `concerns[].id` | string | |
| `concerns[].label` | string | |
| `concerns[].selected_concern_source` | string[] | e.g. `symptoms`, `lab_result`, `family`, `curiosity` |
| `concerns[].selected_family_relation` | object[] | `{ "relation_id", "age_band_id" }` |
| `concerns[].symptom` | object[] | `{ "id", "label", "selected" }` per directive symptom |

```json
{
  "success": true,
  "data": {
    "concern_source": [{ "id": "symptoms", "label": "I'm experiencing symptoms" }],
    "age_band": [{ "id": "under_40", "label": "Under 40" }],
    "family_relation": [{ "id": "mother", "label": "Mother" }],
    "concerns": [
      {
        "id": "heart_bp_high_bp",
        "label": "High Blood Pressure (BP)",
        "selected_family_relation": [{ "relation_id": "mother", "age_band_id": "under_40" }],
        "selected_concern_source": ["lab_result"],
        "symptom": [
          { "id": "heart_bp_high_bp:high_bp_reading", "label": "High BP reading", "selected": true }
        ]
      }
    ]
  }
}
```

### PUT `/session/patient_symptom/`

#### Request body

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `concerns` | array | Yes | Per concern to update |
| `concerns[].id` | string | Yes | Must be session concern id |
| `concerns[].selected_symptom_ids` | string[] | Yes | May be `[]` |
| `concerns[].selected_concern_source_ids` | string[] | Yes | May be `[]` |
| `concerns[].selected_family_relations` | object[] | Yes | May be `[]` |
| `concerns[].selected_family_relations[].id` | string | Yes | PUT field name (`relation_id` on GET) |
| `concerns[].selected_family_relations[].age_band_id` | string | Yes | |

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

**Validation (per concern):**

- `selected_symptom_ids` valid for concern.
- `selected_concern_source_ids` valid directive source ids.
- `lab_result` in sources ↔ `selected_symptom_ids` non-empty (both directions).
- `family` in sources ↔ `selected_family_relations` non-empty (both directions).
- Family entries need valid `id` + `age_band_id`.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Persists symptoms, sources, family history per submitted concern.
- `current_layer` → `patient_concern_probe` when on `patient_symptom`.
- Changed data → cascade reset steps 6, 9.

---

## Step 6 — `patient_concern_probe`

### GET `/session/patient_concern_probe/`

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `functional_impact` | object[] | Directive catalog |
| `duration_impact` | object[] | Directive catalog |
| `progression_impact` | object[] | Directive catalog |
| `concerns` | array | All session concerns |
| `concerns[].id` | string | |
| `concerns[].label` | string | |
| `concerns[].selected_functional_impact` | string | Saved id or `""` |
| `concerns[].selected_duration_impact` | string | Saved id or `""` |
| `concerns[].selected_progression_impact` | string | Saved id or `""` |
| `concerns[].category.label` | string | Parent category label |

```json
{
  "success": true,
  "data": {
    "functional_impact": [{ "id": "significant", "label": "Significant daily impact" }],
    "duration_impact": [{ "id": "lt_3mo", "label": "Less than 3 months" }],
    "progression_impact": [{ "id": "stable", "label": "Stable" }],
    "concerns": [
      {
        "id": "heart_bp_high_bp",
        "label": "High Blood Pressure (BP)",
        "selected_functional_impact": "significant",
        "selected_duration_impact": "6_12mo",
        "selected_progression_impact": "stable",
        "category": { "label": "Heart & Blood Pressure" }
      }
    ]
  }
}
```

### PUT `/session/patient_concern_probe/`

#### Request body

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `concerns` | array | Yes | |
| `concerns[].id` | string | Yes | Session concern id |
| `concerns[].selected_functional_impact_id` | string | Yes | Directive id |
| `concerns[].selected_duration_impact_id` | string | Yes | Directive id |
| `concerns[].selected_progression_impact_id` | string | Yes | Directive id |

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

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Saves impact ids on each submitted concern.
- Runs `ConcernConfidenceEngine`; sets `confidence_score`, `probe_flagged` per concern.
- `current_layer` → `patient_medical_history_context` when on `patient_concern_probe`.
- Changed data → cascade reset step 9 only.

---

## Step 7 — `patient_medical_history_context`

**Headers:** `X-Customer-Profile-ID` optional on GET/PUT (gates reproductive + sexual-health catalogs by profile gender/age).

### GET `/session/patient_medical_history_context/`

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `diagnosis` | object[] | `{ "id", "label", "selected" }` — all directive diagnoses |
| `reproductive_diagnosis` | object[] | Gender-gated; same shape |
| `allergies` | string[] | Free text names |
| `surgeries` | object[] | `{ "name", "area", "performed_when", "reason" }` |
| `medication` | object[] | `{ "name", "dosage", "frequency", "duration" }` |
| `sexual_health_question` | object[] | Gender/age-gated |
| `sexual_health_question[].options` | object[] | `{ "id", "label", "selected" }` |
| `medical_reports` | object[] | See POST response shape |

```json
{
  "success": true,
  "data": {
    "diagnosis": [
      { "id": "hypertension", "label": "Hypertension (BP)", "selected": true },
      { "id": "none", "label": "None", "selected": false }
    ],
    "reproductive_diagnosis": [
      { "id": "endometriosis", "label": "Endometriosis", "selected": false }
    ],
    "allergies": ["Sulfa drugs"],
    "surgeries": [],
    "medication": [
      { "name": "Amlodipine", "dosage": "5mg", "frequency": "Once daily", "duration": "2 years" }
    ],
    "sexual_health_question": [
      {
        "id": "periods",
        "label": "Periods",
        "options": [
          { "id": "regular", "label": "Regular", "selected": false },
          { "id": "irregular", "label": "Irregular", "selected": true }
        ]
      }
    ],
    "medical_reports": [
      {
        "id": "01932f4a-8b2c-7f3e-9c1d-2a4b5c6d7e8f",
        "filename": "cbc_report.pdf",
        "content_type": "application/pdf",
        "size_bytes": 245000,
        "url": "https://cdn.example.com/pre_consultation/medical_reports/.../cbc_report.pdf",
        "uploaded_at": "2026-07-02T12:00:00Z"
      }
    ]
  }
}
```

### POST `/session/patient_medical_history_context/`

Upload medical reports before PUT.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `file` | file | Yes | See below |

**File rules:**

| Rule | Value |
|---|---|
| Max per session | 10 |
| Max size | 10 MB |
| Allowed | PDF, JPEG, PNG, HEIC/HEIF, WebP |
| Blocked | Archives (zip, tar, gz, rar, 7z, …) |
| Layer gate | `current_layer = patient_medical_history_context` |

#### Response `200` `data`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Report id — include in PUT `medical_report_ids` |
| `filename` | string | Original filename |
| `content_type` | string | MIME type |
| `size_bytes` | int | |
| `url` | string | Storage URL (persists until deleted) |
| `uploaded_at` | datetime | ISO 8601 |

```json
{
  "success": true,
  "data": {
    "id": "01932f4a-8b2c-7f3e-9c1d-2a4b5c6d7e8f",
    "filename": "cbc_report.pdf",
    "content_type": "application/pdf",
    "size_bytes": 245000,
    "url": "https://cdn.example.com/pre_consultation/medical_reports/.../cbc_report.pdf",
    "uploaded_at": "2026-07-02T12:00:00Z"
  }
}
```

| Status | When |
|---|---|
| `400` | Wrong layer, invalid file, or max 10 reached |
| `409` | Session completed |

#### Side effects

- Creates `PreConsultationMedicalReport` + storage upload.
- Does **not** advance `current_layer`.

### PUT `/session/patient_medical_history_context/`

#### Request body

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `selected_diagnosis_ids` | string[] | Yes | Directive ids; `none` exclusive |
| `reproductive_diagnosis_ids` | string[] | Yes | Gender-valid ids; may be `[]` |
| `allergies` | string[] | Yes | max 255 per entry; may be `[]` |
| `medication_status` | string | Yes | `no`, `medication`, `supplements`, `medication_supplement` |
| `medications` | object[] | Conditional | Required non-empty unless `medication_status = no` |
| `medications[].name` | string | Yes | max 255 |
| `medications[].dosage` | string | Yes | max 100 |
| `medications[].frequency` | string | Yes | max 100 |
| `medications[].duration` | string | Yes | max 100 |
| `surgeries` | object[] | Yes | May be `[]` |
| `surgeries[].name` | string | Yes | max 255 |
| `surgeries[].area` | string | Yes | max 255 |
| `surgeries[].performed_when` | string | Yes | max 100 |
| `surgeries[].reason` | string | Yes | max 255 |
| `sexual_health_question` | object[] | Yes | May be `[]` |
| `sexual_health_question[].id` | string | Yes | Question id |
| `sexual_health_question[].option_id` | string | Yes | Valid option for question/gender/age |
| `medical_report_ids` | uuid[] | No | Default `[]`; max 10; must exist on session |

```json
{
  "selected_diagnosis_ids": ["hypertension", "prediabetes"],
  "reproductive_diagnosis_ids": [],
  "allergies": ["Sulfa drugs"],
  "medication_status": "medication_supplement",
  "medications": [
    { "name": "Amlodipine", "dosage": "5mg", "frequency": "Once daily", "duration": "2 years" }
  ],
  "surgeries": [],
  "sexual_health_question": [
    { "id": "periods", "option_id": "irregular" }
  ],
  "medical_report_ids": ["01932f4a-8b2c-7f3e-9c1d-2a4b5c6d7e8f"]
}
```

**Validation:**

- No duplicate ids in list fields.
- `none` cannot combine with other diagnosis ids.
- Sexual-health: no duplicate question ids; valid question/option for gender and age.
- `medical_report_ids`: each uuid must belong to session medical history.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Replaces diagnoses, allergies, surgeries, medications, sexual-health answers (full snapshot per collection).
- Syncs medical reports: ids listed kept; omitted ids deleted (row + file).
- Wires `medical_override`: selected diagnoses floor mapped concern `confidence_score` to ≥80.
- Recomputes concern confidence scores.
- `current_layer` → `patient_lifestyle_environment` when on `patient_medical_history_context`.

---

## Step 8 — `patient_lifestyle_environment`

### GET `/session/patient_lifestyle_environment/`

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `lifestyle_field` | array | All directive lifestyle fields |
| `lifestyle_field[].id` | string | e.g. `sleep_duration` |
| `lifestyle_field[].label` | string | |
| `lifestyle_field[].options` | array | `{ "value", "label", "selected" }` |
| `cluster_lifestyle` | array | Empty until first PUT |
| `cluster_lifestyle[].cluster_id` | string | |
| `cluster_lifestyle[].cluster_label` | string | |
| `cluster_lifestyle[].lifestyle_signal_count` | int | |
| `cluster_lifestyle[].lifestyle_signals_triggered` | string[] | |
| `cluster_lifestyle[].lifestyle_contribution` | int | |
| `cluster_confidence` | array | Empty until first PUT |
| `cluster_confidence[].cluster_id` | string | |
| `cluster_confidence[].cluster_label` | string | |
| `cluster_confidence[].base_concern_contribution` | int | |
| `cluster_confidence[].family_risk_contribution` | int | |
| `cluster_confidence[].lifestyle_contribution` | int | |
| `cluster_confidence[].provisional_score` | int | |
| `cluster_confidence[].validation_probed` | boolean | |
| `cluster_confidence[].validation_contribution` | int | |
| `cluster_confidence[].validation_skip_reason` | string \| null | `settled`, `weak_signal`, `not_probed` |
| `cluster_confidence[].final_score` | int | |
| `cluster_confidence[].bucket_id` | string | |
| `cluster_confidence[].bucket_label` | string | |

```json
{
  "success": true,
  "data": {
    "lifestyle_field": [
      {
        "id": "sleep_duration",
        "label": "Sleep",
        "options": [
          { "value": "7-8 hrs", "label": "7-8 hrs", "selected": true }
        ]
      }
    ],
    "cluster_lifestyle": [],
    "cluster_confidence": []
  }
}
```

### PUT `/session/patient_lifestyle_environment/`

Flat JSON object — **all** directive `lifestyle_field` ids required as keys. Values = `options[].value` strings.

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
  "sleep_duration": "6-7 hrs",
  "eating_pattern": "mixed",
  "sugary_drinks": "sometimes",
  "activity_level": "light",
  "desk_job": "yes",
  "stress_level": "moderate",
  "hydration": "1-2L",
  "alcohol": "occasional",
  "tobacco": "none"
}
```

**Validation:** no missing/extra keys; each value must match directive options for that field.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true, "data": { "next_layer": "..." } }` |

```json
{
  "success": true,
  "data": {
    "next_layer": "patient_cluster_probe"
  }
}
```

| `next_layer` value | Meaning |
|---|---|
| `patient_cluster_probe` | Any cluster `final_score` 65–80 → go to step 9 |
| `patient_goals_priorities` | No cluster in range → skip step 9 |

#### Side effects

- Replaces all `PreConsultationLifestyleAnswer` rows.
- Computes and persists `PreConsultationSessionClusterScore` (visible on next GET as `cluster_lifestyle`, `cluster_confidence`).
- `current_layer` → `next_layer` when on `patient_lifestyle_environment`.
- Changed data → cascade reset step 9 only.

---

## Step 9 — `patient_cluster_probe` *(conditional)*

Skip when step 8 `next_layer = patient_goals_priorities`.

### GET `/session/patient_cluster_probe/`

Only concerns in flagged clusters (`final_score` 65–80).

#### Response `data.concerns[]`

| Field | Type | Notes |
|---|---|---|
| `id` | string | Concern id |
| `label` | string | |
| `cluster` | array | Clusters linked to concern |
| `cluster[].id` | string | Cluster id |
| `cluster[].label` | string | |
| `cluster[].cluster_probe` | array | |
| `cluster_probe[].id` | string | Probe id |
| `cluster_probe[].label` | string | |
| `cluster_probe[].value` | int \| null | `0`, `1`, or `null` if unanswered |

```json
{
  "success": true,
  "data": {
    "concerns": [
      {
        "id": "heart_bp_high_cholesterol",
        "label": "High Cholesterol",
        "cluster": [
          {
            "id": "cardiometabolic_risk",
            "label": "Cardiometabolic Risk",
            "cluster_probe": [
              {
                "id": "cardiometabolic_risk_breathless_climbing_stairs",
                "label": "Breathless climbing stairs?",
                "value": null
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### PUT `/session/patient_cluster_probe/`

#### Request body

| Field | Type | Required | Notes |
|---|---|:---:|---|
| `concerns` | array | Yes | Eligible concerns only |
| `concerns[].id` | string | Yes | Must be in a flagged cluster |
| `concerns[].cluster_probe` | array | Yes | All probes for concern required |
| `concerns[].cluster_probe[].id` | string | Yes | Directive probe id |
| `concerns[].cluster_probe[].value` | string \| int \| bool | Yes | Normalized to `0` or `1` |

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

**Validation:**

- Concern must be in a flagged cluster (persisted `final_score` 65–80).
- No duplicate probe ids per concern.
- All valid probe ids for concern required (no missing/extra).
- `value`: `yes`/`no`/`1`/`0`/`true`/`false`.

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Replaces probe answers; updates `probe_question_count`, `probe_positive_count`.
- Recomputes and persists cluster scores (validation contribution applied).
- `current_layer` → `patient_goals_priorities` when on `patient_cluster_probe`.

---

## Step 10 — `patient_goals_priorities`

### GET `/session/patient_goals_priorities/`

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `max_health_goal_count` | int | From directive `max_health_goals` (currently 3) |
| `health_goals` | array | All directive goals |
| `health_goals[].id` | string | |
| `health_goals[].label` | string | |
| `health_goals[].priority` | int \| null | Saved rank or `null` |
| `previous_layer` | string | `patient_cluster_probe` if any cluster flagged 65–80, else `patient_lifestyle_environment` |

```json
{
  "success": true,
  "data": {
    "max_health_goal_count": 3,
    "previous_layer": "patient_cluster_probe",
    "health_goals": [
      { "id": "weight_loss", "label": "Weight loss", "priority": 1 },
      { "id": "balance_hormones", "label": "Balance hormones", "priority": 2 },
      { "id": "improve_energy", "label": "Improve energy", "priority": 3 },
      { "id": "improve_fitness", "label": "Improve fitness", "priority": null }
    ]
  }
}
```

### PUT `/session/patient_goals_priorities/`

**Body is a top-level JSON array** (not wrapped in `{ }`).

| Field | Type | Required | Constraints |
|---|---|:---:|---|
| `[].id` | string | Yes | Directive health goal id |
| `[].priority` | int | Yes | min 1 |

```json
[
  { "id": "weight_loss", "priority": 1 },
  { "id": "balance_hormones", "priority": 2 },
  { "id": "improve_energy", "priority": 3 }
]
```

**Validation:**

- 1 to `max_health_goal_count` entries.
- Unique goal ids; each id valid in directive.
- Priorities must be exactly `1`..`N` where `N` = number of entries (no gaps).

#### Response

| Status | Body |
|---|---|
| `200` | `{ "success": true }` |

#### Side effects

- Replaces all `PreConsultationHealthGoal` rows.
- `current_layer` → `patient_health_map` when on `patient_goals_priorities`.

---

## Step 11 — `patient_health_map`

After step 10 PUT, `current_layer` is `patient_health_map`. Client renders health map from `GET /session/result/`.

| Field | Value |
|---|---|
| `current_layer` | `patient_health_map` |

### GET `/session/result/`

Read-only summary. Call during step 11 (also available after completion).

| Status | When |
|---|---|
| `200` | Session exists |
| `404` | No session |

#### Response `data`

| Field | Type | Notes |
|---|---|---|
| `health_system` | object[] | `{ "label", "icon", "icon-class" }` per explored cluster from directive |
| `cluster_count` | int | Distinct clusters from selected concerns |
| `concern_count` | int | Selected concerns count |
| `lifestyle_context` | object[] | `{ "label", "value" }` per answered lifestyle field |
| `goals` | object[] | `{ "id", "label", "priority" }` ranked goals |

```json
{
  "success": true,
  "data": {
    "health_system": [
      {
        "label": "Metabolic Health",
        "icon": "Activity",
        "icon-class": "icon-activity"
      },
      {
        "label": "Cardiometabolic Risk",
        "icon": "Heart",
        "icon-class": "icon-heart"
      }
    ],
    "cluster_count": 3,
    "concern_count": 5,
    "lifestyle_context": [
      { "label": "Sleep", "value": "6-7 hrs" },
      { "label": "Eating pattern", "value": "Mixed diet" }
    ],
    "goals": [
      { "id": "weight_loss", "label": "Weight loss", "priority": 1 },
      { "id": "balance_hormones", "label": "Balance hormones", "priority": 2 },
      { "id": "improve_energy", "label": "Improve energy", "priority": 3 }
    ]
  }
}
```

---

## Step 12 — POST `/session/complete/`

No request body.

| Status | When | Body |
|---|---|---|
| `200` | Marked completed | `{ "success": true, "data": { "status": "completed", "current_layer" } }` |
| `400` | `current_layer` ≠ `patient_health_map` | `{ "detail": "..." }` |
| `409` | Already completed | `{ "success": false, "data": { ... } }` |
| `404` | No session | |

```json
{
  "success": true,
  "data": {
    "status": "completed",
    "current_layer": "patient_health_map"
  }
}
```

### Side effects

- `status` → `completed`, `completed_at` → now.
- Blocks further layer PUTs (`409`).
