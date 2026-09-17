# Customer-Associate Linking

## Overview

Admin links associates to a **customer profile** at a **center**. Row feeds care-team
UI and related ops. Separate from named appointment `CenterCareTeam`.

---

## Model — `CustomerAssociateAssignment`

Lives in `accounts/customers/models.py`.

```
CustomerAssociateAssignment
├── customer_profile  FK → CustomerProfile
├── associate         FK → Associate
├── center            FK → Center
└── created_by        FK → User (SET_NULL)
```

**Unique constraint:** `(customer_profile, associate, center)`.

---

## URLs

Under `/profiles/` (not nested under centers):

```
GET  /profiles/<profile_uuid>/associates/
GET  /profiles/<profile_uuid>/available-associates/?center_id=
POST /profiles/<profile_uuid>/link-associates/
```

Reverse (associate → profiles):

```
GET  /associates/<associate_uuid>/profiles/
GET  /associates/<associate_uuid>/available-profiles/
POST /associates/<associate_uuid>/link-profiles/
```

Center for link writes comes from body `center_id`. List may use `center_id` query
and/or `X-Center-ID` (header wins on profile associates list).

---

## Views

| View | Method | URL | Action |
|---|---|---|---|
| `CustomerAssociateListView` | GET | `.../associates/` | Linked associates for profile |
| `CustomerLinkAssociateView` | POST | `.../link-associates/` | Add/remove links |
| `CustomerAvailableAssociateView` | GET | `.../available-associates/` | Center associates not yet linked |

Permissions: link POST = `IsAdminUser`. List / available = admin or associate.

---

## POST body — `CustomerAssociateAssignmentSerializer`

```json
{
  "center_id": "<center-uuid>",
  "add": [{ "id": "<associate-uuid>" }],
  "remove": [{ "id": "<associate-uuid>" }]
}
```

Need at least one of `add` / `remove`. Duplicate IDs in a list are ignored (first wins).
Missing profile UUID in path → **404**. Associate must have non-admin
`AssociateCenterAssignment` at that center or → **400**.

Response: `{ "detail": "Create success.", "data": {} }` (sentinel create; no row body).

---

## GET list roles

Roles come from the associate’s center assignment at the **link’s** center
(`roles` / `role_ids`). Prefetch via `associate__center_assignments` + role links —
do **not** use `FilteredRelation` + `prefetch_related` on that alias (Django raises).

---

*Updated: 2026-09-17.*
