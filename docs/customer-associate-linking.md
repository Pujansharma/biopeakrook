# Customer-Associate Linking

## Overview

This document describes the design for linking associates to customer profiles.
An admin assigns an associate to a customer profile within a specific center context.
The link is used downstream by the scheduling engine to match associates with their customers.

---

## Model — `CustomerAssociateAssignment`

Lives in `accounts/customers/models.py`.

```
CustomerAssociateAssignment
├── customer_profile  FK → CustomerProfile
├── associate         FK → Associate
├── center            FK → Center
├── is_primary        BooleanField (default False)
└── assigned_by       FK → User (SET_NULL)
```

**Unique constraint:** `(customer_profile, associate, center)` — the same associate
can be linked to the same profile at different centers independently (e.g., an
associate who works at two centers can serve the same customer at both).

The `center` FK is set from the URL path at creation time. It is never inferred
from the profile's center assignments.

---

## URL Structure

Nested under the centers namespace, scoped to a customer profile:

```
/centers/<center_id>/customer-profiles/<profile_id>/associates/
/centers/<center_id>/customer-profiles/<profile_id>/associates/available/
/centers/<center_id>/customer-profiles/<profile_id>/associates/<pk>/
```

Center context comes from `<center_id>` in the URL path — no `X-Center-ID` header.

---

## Views

| View | Method | URL | Action |
|---|---|---|---|
| `CustomerAssociateView` | GET | `.../associates/` | List assigned associates for this profile+center |
| `CustomerLinkAssociateView` | POST | `.../associates/` | Link an associate to this profile+center |
| `CustomerAvailableAssociateView` | GET | `.../associates/available/` | List associates at this center not yet linked to this profile |
| _(future)_ | DELETE | `.../associates/<pk>/` | Unlink an associate |

---

## Permissions

All views: `IsAdminUser` only. No associate-level access.

---

## Business Rules

- The associate must have an active `AssociateCenterAssignment` at the given center
  to be eligible for linking. This is validated at creation time in the serializer.
- The customer profile must have a `CustomerCenterAssignment` at the given center.
  Linking an associate to a profile at a center the profile does not belong to is rejected.
- `is_primary` can only be `True` for one associate per `(customer_profile, center)` pair.
  Setting a new primary automatically unsets the previous one.

---

## Serializer — `CustomerAssociateAssignmentSerializer`

Read fields: associate name, role, assignment metadata.
Write field: `associate_id` (UUID). Center and profile come from view context, not the request body.

---

*Written: April 2026.*
