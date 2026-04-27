# Associate RBAC v2 — URL-Based Center Context

## Overview

This document describes the v2 RBAC design for associates. Center context moves
from the `X-Center-ID` request header into the URL path. Associates and admins
share one URL namespace, one set of views, and one serializer per resource.
Permission classes gate access entirely — no serializer switching, no filtered
responses.

---

## What Changed and Why

### v1 (Header-Based)

Associates sent `X-Center-ID`. `CenterContextMiddleware` extracted it into
`request.center_id`. Associate views lived on separate routes with separate
serializers:

```
GET /centers/associates/          # associate route (header: X-Center-ID: <uuid>)
GET /centers/<uuid>/associates/   # admin route (center from URL)
```

### v2 (URL-Based)

Center ID is in the URL. One route, one view, one serializer. Permission classes
decide who gets in; everyone who gets in sees the same response.

```
GET /centers/<uuid>/associates/   # single route — admin, center admin, and permitted associates
```

---

## URL Structure

```
/centers/                                        # list centers
/centers/<center_id>/                            # center detail
/centers/<center_id>/operating-hours/            # operating hours
/centers/<center_id>/associates/                 # associate assignments
/centers/<center_id>/associates/<pk>/            # specific assignment
/centers/<center_id>/associate-roles/            # roles
/centers/<center_id>/associate-roles/<pk>/       # specific role
/centers/<center_id>/rooms/                      # rooms
/centers/<center_id>/rooms/<pk>/                 # specific room
/centers/<center_id>/rooms/<pk>/schedules/       # room schedules
/centers/<center_id>/equipments/                 # equipment
/centers/<center_id>/equipments/<pk>/            # specific equipment
/centers/<center_id>/equipments/<pk>/schedules/  # equipment schedules
/centers/<center_id>/customer-profiles/          # customer profiles
/centers/<center_id>/customer-profiles/<pk>/     # specific customer profile
```

---

## Access Tiers

| User | Condition | Result |
|---|---|---|
| System admin (`IsAdminUser`) | Always | Full access |
| Associate | `is_admin=True` on center assignment | Full access |
| Associate | Role has `ALL` feature | Full access |
| Associate | Role has required feature(s) | Access to that endpoint only |
| Associate | Role missing required feature(s) | 403 Denied |
| Associate | No assignment at this center | 403 Denied |

There is no partial/filtered response. An associate either has access to an
endpoint or receives a 403. Query results are not narrowed based on role level.

---

## Permission Classes

### BaseAssociateRBACPermission

Validates:
1. User is an associate (`IsAssociateUser`)
2. Associate object exists on `request.user`
3. `center_id` kwarg is present in the URL
4. Associate has an active `AssociateCenterAssignment` at that center

Sets `request.center_assignment` for downstream object-level checks.
Does **not** set `request.center_id` — views read center context from
`self.kwargs['center_id']` directly.

```python
@staticmethod
def get_center_id(request, view):
    return view.kwargs.get('center_id')
```

### AssociateAdminPermission

Extends `BaseAssociateRBACPermission`. Requires `is_admin=True` on the
assignment. Grants the same full access as `IsAdminUser` within the center.

### AssociateFeaturePermission

Extends `BaseAssociateRBACPermission`. Returns 403 if the role does not have
ANY of `required_any_features`. If role has `ALL`, passes unconditionally.

### Feature-Specific Classes

| Class | Required Feature |
|---|---|
| `AppointmentFeaturePermission` | `APPOINTMENTS` |
| `AssociateOnboardingPermission` | `ASSOCIATE_ONBOARDING` |
| `CustomerOnboardingPermission` | `CUSTOMER_ONBOARDING` |
| `PackagesPermission` | `PACKAGES` |

---

## Permission Composition Patterns

### Full access: system admin, center admin, or ALL-role associate

```python
permission_classes = [IsAdminUser | AssociateAdminPermission | AssociateFeaturePermission]
```

`AssociateFeaturePermission` with empty `required_any_features` passes for any
associate with a valid assignment, including `ALL`-role associates. Use this
when the endpoint is open to all center members.

### Feature-gated (admin always in, feature required for associates)

```python
permission_classes = [IsAdminUser | AssociateAdminPermission | AppointmentFeaturePermission]
```

### Read/write split by role

```python
permission_classes = [
    IsAdminUser |
    (AssociateAdminPermission & ReadUpdateOnly) |
    (AssociateFeaturePermission & ReadUpdateOnly)
]
```

---

## View Consolidation

Duplicate view pairs are collapsed into one. `get_queryset` and
`perform_create` read center context from `self.kwargs['center_id']`
exclusively.

| v1 Admin View | v1 Associate View | v2 Unified View |
|---|---|---|
| `CenterDetailView` | `AssociateCenterDetailView` | `CenterDetailView` |
| `CenterAssociateListView` | `AssociateCenterAssociateListView` | `CenterAssociateListView` |
| `CenterAssociateRolesListView` | `AssociateCenterRolesListView` | `CenterAssociateRolesListView` |
| — | `AssociateCenterRoleDetailView` | `CenterAssociateRoleDetailView` |
| — | `AssociateCenterRoomListView` | `CenterRoomListView` |
| — | `AssociateCenterRoomDetailView` | `CenterRoomDetailView` |
| — | `AssociateCenterRoomScheduleListView` | `CenterRoomScheduleListView` |
| — | `AssociateCenterEquipmentListView` | `CenterEquipmentListView` |
| — | `AssociateCenterEquipmentDetailView` | `CenterEquipmentDetailView` |
| — | `AssociateCenterEquipmentScheduleListView` | `CenterEquipmentScheduleListView` |
| `CenterUUIDCustomerProfilesView` | `CenterCustomerProfilesView` | `CenterCustomerProfilesView` |
| — | `CenterCustomerProfileDetailView` | `CenterCustomerProfileDetailView` |

---

## Object-Level Business Rules

Permission classes handle endpoint access. Object-level rules remain in views
and are enforced via `get_object` and `perform_update`. `request.center_assignment`
is still available for these checks.

| Rule | Where enforced |
|---|---|
| Associate cannot modify themselves | View `get_object` |
| Non-admin cannot modify `ALL`-role assignment | View `get_object` |
| Non-admin cannot assign a role with `ALL` feature | View `perform_update` |

---

## What Is Retired

| Component | Status | Reason |
|---|---|---|
| `CenterContextMiddleware` | Removed | No request-level center context needed |
| `X-Center-ID` header | Removed | Center ID is in the URL |
| `CenterHeaderMetaView` | Removed | Used only to resolve center from header |
| `request.center_id` mutation in permission class | Removed | Views use `self.kwargs['center_id']` |
| Header-only associate routes (`centers/detail/`, `centers/rooms/`, etc.) | Removed | Replaced by unified `centers/<center_id>/...` |
| Duplicate associate-scoped view classes | Removed | Collapsed into unified views |
| `CustomerProfileContextMiddleware` | Kept | `X-Customer-Profile-ID` is unchanged |

---

*Written: April 2026. Supersedes header-based center context from `associate-roles-rbac.md`.*
