# Associate Roles & RBAC

## Overview

Associates are center-linked users who access the CenterAdmin Portal. Each associate can be assigned to multiple centers via `AssociateCenterAssignment`, with a per-center role and admin flag controlling access.

This document covers the current RBAC implementation and the planned evolution toward granular feature + ability permissions.

---

## Models

### AssociateRole

Defines a named role with a set of features. Scoped to a specific center.

| Field | Type | Purpose |
|-------|------|---------|
| `name` | CharField | Role label (e.g., "Receptionist", "Specialist") |
| `features` | ArrayField(CharField) | List of granted features (current) |
| `center` | FK(Center) | Center this role belongs to |
| `role_tag` | CharField | `clinical` or `non_clinical` |
| `is_external` | BooleanField | External associate role |
| `is_system` | BooleanField | System-generated role (not editable) |
| `summary` | JSONField | Denormalized permission cache (future) |

Constraint: `UniqueConstraint(center, Lower(name), condition=center IS NOT NULL)` — role name unique per center (case-insensitive). Same name allowed across centers. System roles (`center=NULL`) excluded.

### AssociateRolePermission (Future)

Granular per-feature ability. Not used in permission checks yet.

| Field | Type | Purpose |
|-------|------|---------|
| `role` | FK(AssociateRole) | Parent role |
| `feature` | CharField | Feature key (e.g., `appointments`) |
| `ability` | CharField | `manage`, `read`, or `none` |

Constraint: `UniqueConstraint(fields=['role', 'feature'])`

### AssociateCenterAssignment

Links an associate to a center with a role and admin flag.

| Field | Type | Purpose |
|-------|------|---------|
| `associate` | FK(Associate) | The associate |
| `center` | FK(Center) | The center |
| `role` | FK(AssociateRole) | Role at this center |
| `is_admin` | BooleanField | Center admin flag |
| `mode` | CharField | `virtual`, `in_person`, or `both` |
| `is_primary` | BooleanField | Primary center flag |

Constraint: `UniqueConstraint(fields=['associate', 'center'])` -- one role per associate per center.

---

## Features & Constants

### AssociateRoleFeature

| Constant | Value | Description |
|----------|-------|-------------|
| `ALL` | `"all"` | Grants access to all features |
| `CUSTOMER_ONBOARDING` | `"customer_onboarding"` | Customer onboarding workflows |
| `ASSOCIATE_ONBOARDING` | `"associate_onboarding"` | Associate onboarding workflows |
| `APPOINTMENTS` | `"appointments"` | Appointment management |
| `APPOINTMENT_DATA_SCOPE` | `"appointment_data_scope"` | Appointment data visibility scope |
| `PACKAGES` | `"packages"` | Package management |

### AssociateRoleAbility (Future)

| Constant | Value | Description |
|----------|-------|-------------|
| `MANAGE` | `"manage"` | Full CRUD access |
| `READ` | `"read"` | Read-only access |
| `NONE` | `"none"` | No access |

**Current behavior:** A feature in the `features` array grants full access (equivalent to `MANAGE`).

---

## Permission Classes

### Inheritance Hierarchy

```
IsAuthenticated
  +-- IsAdminUser              (account_type == 'admin')
  +-- IsAssociateUser          (account_type == 'associate')
  |     +-- BaseAssociateRBACPermission   (associate + center assignment)
  |           +-- AssociateAdminPermission (is_admin == True)
  |           +-- AssociateFeaturePermission (role has required features)
  |                 +-- AppointmentFeaturePermission
  |                 +-- AssociateOnboardingPermission
  |                 +-- CustomerOnboardingPermission
  |                 +-- PackagesPermission
  +-- IsCustomerUser           (account_type == 'customer')
```

### BaseAssociateRBACPermission

Base class for all associate RBAC checks. Validates:

1. User is an associate (`IsAssociateUser`)
2. Associate object exists on user
3. `X-Center-ID` header is present
4. Associate has an active `AssociateCenterAssignment` at that center

Stashes `request.center_id` and `request.center_assignment` for downstream use.

Does NOT check admin status or features.

### AssociateAdminPermission

Extends `BaseAssociateRBACPermission`. Requires `is_admin=True` on the center assignment.

Use for endpoints only center admins should access (e.g., managing other associates' roles).

### AssociateFeaturePermission

Extends `BaseAssociateRBACPermission`. Checks that **any** of the associate's multi-roles on the center assignment has ANY of `required_any_features` (OR across roles).

- If `required_any_features` is empty, allows access.
- If role has `AssociateRoleFeature.ALL`, allows access.
- Otherwise, for each linked active role: if `ALL` in features or any required feature matches → allow.

Does NOT include an admin bypass. Use `|` composition with `AssociateAdminPermission` if admins should also have access.

### Feature-Specific Permission Classes

| Class | Features |
|-------|----------|
| `AppointmentFeaturePermission` | `[APPOINTMENTS]` |
| `AssociateOnboardingPermission` | `[ASSOCIATE_ONBOARDING]` |
| `CustomerOnboardingPermission` | `[CUSTOMER_ONBOARDING]` |
| `PackagesPermission` | `[PACKAGES]` |

---

## Usage Patterns

### Admin-only endpoint

```python
permission_classes = [AssociateAdminPermission]
```

### Feature-gated endpoint (admin also allowed)

```python
permission_classes = [AssociateAdminPermission | AppointmentFeaturePermission]
```

### Feature-gated endpoint (admin NOT allowed unless they have the feature)

```python
permission_classes = [AppointmentFeaturePermission]
```

### Mixed: system admin OR center admin OR feature holder

```python
permission_classes = [
    IsAdminUser |
    AssociateAdminPermission |
    AppointmentFeaturePermission
]
```

### With HTTP method restrictions

```python
permission_classes = [
    IsAdminUser |
    (AssociateAdminPermission & ReadUpdateOnly) |
    (AssociateFeaturePermission & ReadUpdateOnly) |
    (IsAssociateUser & ReadOnly)
]
```

---

## Query Caching

`get_associate_roles()` caches the assignment lookup on the request object using `_center_assignment`. When multiple permission classes in a `|` chain call the base class, the DB query runs only once per request.

```
AssociateAdminPermission | AppointmentFeaturePermission
       |                            |
       v                            v
  BaseAssociateRBACPermission  BaseAssociateRBACPermission
       |                            |
  get_associate_roles()        get_associate_roles()
       |                            |
    DB query                  returns cached result
```

---

## Object-Level & Field-Level Business Rules

Permission classes handle endpoint-level access. Object-level and field-level rules are handled in views and serializers:

| Concern | Where |
|---------|-------|
| Can this user type access this endpoint? | `permission_classes` |
| Can this user modify this specific associate? | View (`get_object`) |
| Can this user modify this specific field (e.g., role)? | Serializer or view |

Examples of object-level rules (enforced in views):
- Associates cannot modify themselves
- Non-admin associates with `ALL` access cannot modify associates who also have `ALL` access
- Only center admins can update roles for all associates

---

## Future: Granular Permissions

### Phase 1 (Current)

`features` ArrayField on `AssociateRole`. Each feature in the array grants full access.

```
features = ['appointments', 'packages']
-- Full access to appointments and packages
```

### Phase 2: AssociateRolePermission

`AssociateRolePermission` rows define per-feature ability levels:

```
(role, "appointments", "manage")   -- Full CRUD
(role, "packages", "read")         -- Read only
(role, "appointment_data_scope", "center_all")  -- See all center data
```

### Phase 3: Summary Cache

On each `AssociateRolePermission` create/update, the `summary` JSONField on `AssociateRole` is populated:

```json
{
    "appointments": "manage",
    "packages": "read",
    "appointment_data_scope": "center_all"
}
```

Permission checks read from `role.summary` instead of querying `AssociateRolePermission`. Single query via `select_related('role')` is preserved.

### Migration Path

```
Phase 1:  ['appointments', 'packages']
            |
            v  (data migration)
Phase 2:  (role, "appointments", "manage")
          (role, "packages", "manage")
            |
            v  (denormalize)
Phase 3:  summary = {"appointments": "manage", "packages": "manage"}
```

### Permission Check Evolution

```python
# Phase 1 (current):
AssociateRoleFeature.ALL in role.features
any(f in role.features for f in self.required_any_features)

# Phase 3 (future):
role.summary.get('all') == 'manage'
role.summary.get(feature, 'none') in ('read', 'manage')
```

View-level permission class declarations remain unchanged across all phases.

### Role Templates (Future Reference)

| Role | Customer Onboarding | Associate Onboarding | Appointments | Data Scope | Packages |
|------|--------------------|--------------------|-------------|------------|----------|
| Center Admin | manage | manage | manage | center_all | manage |
| Center Co-Admin | manage | read | manage | center_all | read |
| Specialist Internal | manage | none | manage | center_all | read |
| Specialist External | read | none | manage | only_assigned | read |
