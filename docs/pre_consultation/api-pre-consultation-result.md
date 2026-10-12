# Pre-Consultation Result API

**Base:** `/pre-consultation/result/`

**Auth:** `Authorization: Bearer <access_token>` — **admin or associate** only (customer tokens → `403`)

**Purpose:** List sessions and read a customer's completed/in-progress session by **`user_id` UUID** (not the caller's own session).

**Workflow:** `GET /list/` → pick `user_id` → `GET /<user_id>/…`

**OpenAPI:** tag `Pre-Consultation Result` in `/pre-consultation/openapi/`

**Session wizard:** [api-pre-consultation-v1.md](./api-pre-consultation-v1.md) · [api-pre-consultation-v2.md](./api-pre-consultation-v2.md) · [simulation.md](./simulation.md)

**Bruno:** folder `bruno/pre-consultation-result/` (staff `Bearer {{access_token}}`)

---

## Global rules

| Rule | Detail |
|---|---|
| Lookup key | `<user_id>` = customer `User` UUID |
| Envelope | `{ "success": true, "data": { ... } }` |
| List envelope | `{ "success", "count", "next", "previous", "data": [...] }` |
| `404` | No session for user |
| `401` | Missing/invalid JWT |
| `403` | Customer account or other disallowed `user_type` |

---

## GET `/result/list/`

| Param | Default | Notes |
|---|---|---|
| `search` | — | Name, phone, or email (prefix match) |
| `page` | `1` | |
| `limit` | `10` | max `50` |

### Response `data[]`

| Field | Type |
|---|---|
| `user_id` | UUID |
| `id` | UUID (session) |
| `contact_email` | string \| null |
| `phone` | string \| null |
| `first_name` | string \| null |
| `last_name` | string \| null |
| `gender` | string \| null (`Male`, `Female`, `Other`) |
| `date_of_birth` | date \| null |
| `height` | float \| null (cm from main `CustomerProfile.height_cm`) |
| `weight` | float \| null (kg from main `CustomerProfile.weight_kg`) |
| `status` | `In Progress` \| `Completed` |

---

## GET `/<user_id>/overview/`

| Field | Type |
|---|---|
| `summary` | string |
| `checklist` | `{ "id", "done", "identified_concern" }[]` |
| `patient_goals` | `{ "id", "label", "priority" }[]` |

---

## PATCH `/<user_id>/checklist/<item_id>/`

```json
{ "done": true }
```

Response `data`: `id`, `done`, `identified_concern`

| Status | When |
|---|---|
| `404` | Session or item not found |

---

## GET `/<user_id>/context/`

| Field | Type |
|---|---|
| `quick_summary` | string |
| `top_5_concerns` | `{ "label", "confidence_score", "concern_bucket" }[]` |
| `top_3_clusters` | `{ "label", "concern_count" }[]` |
| `current_medications` | `{ "label", "dosage", "frequency" }[]` — when on medication |
| `know_diagnosis` | `{ "label", "progression_impact" }[]` |

---

## GET `/<user_id>/family-risk/`

| Field | Type |
|---|---|
| `patient` | `{ "name", "age" }` |
| `family_relations` | `{ "label", "age_band", "flagged_concern" }[]` |
| `family_concern_count` | object (concern label → count) |
| `family_risk_summary` | string |
| `family_history_cluster_contribution` | `{ "cluster", "concern", "contribution_bucket" }[]` |

---

## GET `/<user_id>/health-map/`

`data.concerns[]` sorted by confidence desc:

| Field | Type |
|---|---|
| `label` | string |
| `duration_impact` | string |
| `functional_impact` | string |
| `concern_bucket` | string |
| `progression_impact` | string |
| `evidence_count` | int |
| `has_family_history` | bool |
| `map_cluster_count` | int |

---

## GET `/<user_id>/clusters/`

Non-zero scores only.

| Field | Type |
|---|---|
| `label` | string |
| `cluster_bucket` | string |
| `evidence_points` | int |
| `concerns` | string[] |
| `supporting_diagnosis` | string[] |
| `family_history` | string[] |
| `lifestyle_factors` | string[] |
| `probe` | string[] |

---

## GET `/<user_id>/lifestyle/`

`data.life_style[]`:

| Field | Type |
|---|---|
| `label` | string |
| `answer` | string |
| `mapped_concerns` | string[] |
| `mapped_clusters` | string[] |

---

## GET `/<user_id>/medical-context/`

| Field | Type |
|---|---|
| `diagnosis` | `{ "label", "mapped_cluster" }[]` |
| `medications` | `{ "label", "frequency", "dosage", "duration" }[]` — when `medication` or `medication_supplement` |
| `suppliments` | same shape — when `supplements` or `medication_supplement` |
| `surgeries` | string[] (names only) |

---

## GET `/<user_id>/surgery/`

Structured surgery history.

| Field | Type |
|---|---|
| `name` | string |
| `performed_when` | string |
| `reason` | string |

---

## GET `/<user_id>/medical-reports/`

| Field | Type | Notes |
|---|---|---|
| `name` | string | |
| `download_url` | string | |
| `report_summary` | string | `""` if no summary yet |
| `testing_location` | string | `""` if none |
| `testing_date` | date \| null | |
| `is_flagged` | bool | `false` if no summary |

---

## GET `/<user_id>/raw-data/`

Flattened layer answers for export.

| Field | Type |
|---|---|
| `patient_baseline` | `{ "name", "sex", "age", "city", "height", "weight" }` — height cm / weight kg (`null` until set) |
| `patient_category` | string[] |
| `patient_concern` | `{ "concern": { "label", "health_system" } }[]` |
| `patient_symptom` | string[] |
| `patient_concern_probe` | `{ "concern", "label" }[]` |
| `patient_cluster_probe` | `{ "question", "answer" }[]` |
| `patient_medical_diagnosis` | string[] |
| `patient_medications_suppliments` | string[] |
| `patient_allergies` | string[] |
| `patient_sexual_health` | `{ "question", "answer" }[]` |
| `patient_family_medical_history` | `{ "relation", "age_band", "concern" }[]` |
| `patient_surgeries` | `{ "name", "performed_when", "reason" }[]` |
| `patient_lifestyle_environment` | string[] |
| `patient_goals_priorities` | string[] |

---

## GET / POST `/<user_id>/notes/`

**GET** `data.notes[]`: `note`, `category`, `created_at`

**POST** body:

```json
{
  "note": "Follow up on lipid panel.",
  "category": "investigation"
}
```

`category`: `general`, `investigation`, `treatment`, `follow_up`, `question`

Response `201`: `{ "success": true, "data": { "note", "category", "created_at" } }`

---

## Endpoint index

| Method | Path |
|---|---|
| GET | `/pre-consultation/result/list/` |
| GET | `/pre-consultation/result/<user_id>/overview/` |
| PATCH | `/pre-consultation/result/<user_id>/checklist/<item_id>/` |
| GET | `/pre-consultation/result/<user_id>/context/` |
| GET | `/pre-consultation/result/<user_id>/family-risk/` |
| GET | `/pre-consultation/result/<user_id>/health-map/` |
| GET | `/pre-consultation/result/<user_id>/clusters/` |
| GET | `/pre-consultation/result/<user_id>/lifestyle/` |
| GET | `/pre-consultation/result/<user_id>/medical-context/` |
| GET | `/pre-consultation/result/<user_id>/surgery/` |
| GET | `/pre-consultation/result/<user_id>/medical-reports/` |
| GET | `/pre-consultation/result/<user_id>/raw-data/` |
| GET | `/pre-consultation/result/<user_id>/notes/` |
| POST | `/pre-consultation/result/<user_id>/notes/` |
