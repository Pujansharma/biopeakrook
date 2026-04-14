# Accounts Architecture

## The Shared Foundation: `User`

`User` (`accounts/users/models.py`) is the single authentication identity for everyone on the platform. It holds only what is universal across all user types:

- UUID primary key, email, phone (auth credentials)
- `first_name`, `last_name`, `date_of_birth`, `gender`, `image` (via `AbstractUserProfile`)
- `is_active`, `is_staff`, `date_joined` (Django auth machinery)

The `account_type` claim on the JWT token (`admin`, `associate`, `customer`) is the divergence point. Everything below this line is type-specific.

---

## Associates (`accounts/associates/`)

Associates are **center-linked staff** — the operational workforce of the platform.

| Model | Purpose |
|---|---|
| `Associate` | Thin 1:1 extension of `User`. Holds only `is_external` and `created_by`. |
| `AssociateRole` | A named role scoped to a center. Carries `features` (ArrayField), `role_tag` (`clinical`/`non_clinical`), `is_external`, `is_system`, and `summary` (future denorm cache). |
| `AssociateRolePermission` | Future granular `(role, feature, ability)` rows — `manage`/`read`/`none` per feature. |
| `AssociateCenterAssignment` | The binding row. Links associate ↔ center with `role`, `is_admin`, `mode`, `is_primary`, `effective_from/until`. |

**Key constraint:** `UniqueConstraint(['associate', 'center'])` — one role per associate per center. A single associate can work at multiple centers with different roles.

---

## Customers (`accounts/customers/`)

Customers are **end users booking services** — not staff, not RBAC subjects.

| Model | Purpose |
|---|---|
| `Customer` | Thin 1:1 extension of `User`. No operational fields at all. |
| `CustomerProfile` | A bookable identity (family member support). Inherits `AbstractUserProfile`. Adds `is_primary`, `is_onboarding_complete`. Each `Customer` can have multiple profiles. |
| `CustomerOnboarding` | Health data per profile: `height`, `weight`, units. 1:1 with `CustomerProfile`. |
| `CustomerCenterAssignment` | Links a profile to a center. `is_primary` flag. `UniqueConstraint(['customer_profile', 'center'])`. |

---

## Why This Segmented Architecture Is Correct

A flat `User` table approach — putting every field on one model and toggling behavior by type — is a common anti-pattern. Here is why the breakout is justified for each type.

### Associates do not need health data

An associate's `is_external` flag and center assignment are their defining operational attributes. `height`, `weight`, `is_onboarding_complete`, and family profiles (`CustomerProfile`) would be dead columns on every associate row — null-padded noise.

### Associates do not need a payment flag

`is_onboarding_complete` on `CustomerProfile` tracks whether a customer has completed intake (health data + payment). That lifecycle is meaningless for associates — their onboarding is administrative (`AssociateCenterAssignment`), not consumer-side.

### Customers do not need RBAC

The entire `AssociateRole` + `AssociateCenterAssignment` + `AssociateRolePermission` stack is center-scoped feature gating. A customer never needs to be asked "what center are you acting on behalf of?" via `X-Center-ID`. They access endpoints as end consumers. Attaching RBAC columns and permission checks to customers would force every customer request through machinery that cannot apply to them.

### `CustomerProfile` enables family booking without multiple `User` accounts

A single `Customer` (one login) can have multiple `CustomerProfile` rows — primary member plus dependants. Each profile can be assigned to different centers and carries its own health onboarding. Associates have no equivalent concept: one associate, one identity, multi-center via `AssociateCenterAssignment`.

### Permission classes stay clean

The separation means `IsAssociateUser`, `IsCustomerUser`, and `IsAdminUser` are clean, non-overlapping type checks at the API layer. `BaseAssociateRBACPermission` can safely assume `request.user.associate` exists. `IsCustomerUser` endpoints never touch the RBAC stack at all.

### Schema integrity

With separate models, database constraints enforce correctness by type. An `AssociateCenterAssignment` row cannot accidentally reference a customer. A `CustomerOnboarding` row cannot be created for an associate profile. The FK chains themselves make illegal states unrepresentable.

---

## Summary

The accounts section treats `User` as a pure authentication token and pushes every operational concern into type-specific satellite models. Each model carries exactly the fields its type needs and none it does not. This keeps queries lean, constraints meaningful, and permission logic unambiguous.
