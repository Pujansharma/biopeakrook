# CLAUDE.md — Biopeak Nexus Agent Instructions

This file configures Claude Code's behavior for the **Biopeak Nexus** project.
Read this before every session.

---

## 1. Memory

**All persistent memories for this project are stored exclusively in `docs/MEMORY.md`.**

> **STRICT REQUIREMENT:** Never write to or read from the standard Claude Code memory directory
> (`~/.claude/projects/...`).
> That directory must NOT be used for this project under any circumstances.
> `docs/MEMORY.md` is the one and only memory store.

- Before starting any task, check `docs/MEMORY.md` for relevant context.
- Save important decisions, patterns, user preferences, and non-obvious project facts to `docs/MEMORY.md`.
- Do NOT save things derivable from reading the code, git history, or other docs.
- Keep entries dated and concise. Remove stale entries when they no longer apply.

---

## 2. Coding Rules

**Strictly follow `docs/CODING_RULES.md` for all code written in this project.**

Key non-negotiables (see the full file for examples and rationale):
- No raw SQL — Django ORM only (`raw()`, `RawSQL`, cursor execution are forbidden)
- No nested functions — all functions at module or class level
- No `try/except` for control flow or "just in case" — exceptions are for exceptional cases only
- No imports inside functions — all imports at the top of the file
- No star imports
- Vectorize with pandas/numpy — never loop over DataFrames
- f-strings only — no `%` or `.format()`
- Generators for large data — avoid loading everything into memory
- Type hints on all public functions
- Dict dispatch instead of long if/elif chains
- Single responsibility per function

**All documentation goes in `docs/`.** No stray `.md` files in the root or random folders.

---

## 3. Package Versions — Always Use Latest

**This project always uses the latest stable versions of all packages.**
When suggesting new packages or upgrades, **check PyPI or the official release page** for the current latest version — do not guess or use knowledge-cutoff versions.

Current locked versions (from `uv.lock` — last synced April 2026):

| Package | Version |
|---|---|
| Python | ≥ 3.14 (use 3.14.x latest stable) |
| Django | 6.0.3 |
| djangorestframework | 3.17.1 |
| djangorestframework-simplejwt | 5.5.1 |
| psycopg (PostgreSQL driver) | 3.3.3 |
| Pillow | 12.1.1 |
| gunicorn | 25.3.0 |
| whitenoise | 6.12.0 |
| pandas | 3.0.2 |
| requests | 2.33.1 |
| python-decouple | 3.8 |
| phonenumbers | 9.0.26 |
| pyotp | 2.9.0 |
| qrcode | 8.2 |
| django-cors-headers | 4.9.0 |
| django-debug-toolbar | 6.2.0 |
| asgiref | 3.11.1 |

To add a package: `uv add <package>` (never `pip install`).
To upgrade all: `uv sync --upgrade`.

---

## 4. Project Architecture

### 4.1 Overview

**Biopeak Nexus** is a multi-center healthcare and wellness operations management platform.
It handles people management (associates, customers), room and equipment management,
appointment scheduling, service catalogues, and packages.

### 4.2 Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.14.x |
| Web Framework | Django | 6.0.3 |
| API Layer | Django REST Framework | 3.17.1 |
| Authentication | djangorestframework-simplejwt | 5.5.1 |
| Database | PostgreSQL | 17 |
| DB Driver | psycopg (v3) | 3.3.3 |
| App Server | Gunicorn | 25.3.0 |
| Static Files | WhiteNoise | 6.12.0 |
| Data Processing | pandas | 3.0.2 |
| Package Manager | uv | latest |
| Containerization | Docker (multi-stage) | — |
| Cloud | AWS (ECS, RDS, S3, SES, CloudFront) | — |

### 4.3 Django Application Map

```
biopeak-nexus/
├── core/                        # Django project root
│   ├── settings/
│   │   ├── base.py              # Shared settings (AUTH_USER_MODEL, REST_FRAMEWORK, SIMPLE_JWT)
│   │   ├── development.py       # Local dev: SQLite-compatible Postgres, debug toolbar
│   │   ├── staging.py           # Staging environment
│   │   └── production.py        # AWS S3 storage, SES email, RDS Postgres
│   ├── api/urls.py              # Top-level API URL router
│   └── utils/                   # Shared base classes and utilities
│       ├── models.py            # BaseModel, BaseUUIDModel (uuid7 PK)
│       ├── serializers.py       # BaseModelSerializer
│       ├── views/               # BaseGenericAPIView, BaseRetrieveUpdateAPIView
│       ├── permissions.py       # IsAdminUser, IsAssociateUser, IsCustomerUser, RBAC classes
│       ├── middleware.py        # CenterContextMiddleware, CustomerProfileContextMiddleware
│       ├── authentication.py    # BaseJWTAuthentication + custom token claims
│       ├── exceptions.py        # base_exception_handler, 404/500 handlers
│       ├── pagination.py        # BasePageNumberPagination (10 items/page)
│       └── fields.py            # PhoneNumberField, PhoneNumberSerializerField
│
├── accounts/                    # All user/identity management
│   ├── users/                   # Custom User model (email-based auth, UUID PK)
│   ├── associates/              # Internal staff: Associate, AssociateRole, AssociateCenterAssignment
│   ├── centers/                 # Centers: Center, CenterOperatingHour, CenterClosure
│   ├── customers/               # End users: Customer, CustomerProfile, CustomerOnboarding
│   ├── verifications/           # OTP flows, email verification
│   └── audits/                  # Audit log models
│
├── appointments/                # Scheduling engine
│   ├── models.py                # Schedule, Appointment, BlockedPeriod, AppointmentHistory
│   └── utils/
│       ├── intervals.py         # Pure interval arithmetic (no Django dependency)
│       ├── scheduling.py        # DB-aware slot finder
│       ├── db.py                # Appointment CRUD helpers
│       └── constants.py         # AppointmentStatus, AppointmentModes
│
├── services/                    # Service catalogue
│   ├── models.py                # Service, ServiceRequirement
│   ├── packages/                # Service bundles: Composite, CompositeService
│   └── utils/constants.py       # ServiceCategory
│
├── inventory/                   # Physical resources
│   ├── models.py                # Room, RoomSchedule, Equipment, EquipmentSchedule,
│   │                            # EquipmentBooking, EquipmentMaintenance
│   └── utils/constants.py       # RoomType, DeviceType
│
├── sequences/                   # Alphanumeric ID/code generation
├── webhooks/                    # Webhook support (future)
│
├── integrations/
│   └── google_calendar/         # Google Calendar sync (see docs/google-calendar-integration.md)
│       ├── google_oauth.py      # Consent URL, code exchange, token refresh, revoke
│       ├── calendar_api.py      # insert_event/patch_event/delete_event
│       ├── tokens.py            # get_valid_access_token() — refresh-if-expired glue
│       ├── db.py                # Persist tokens onto GoogleCalendarConnection
│       ├── connections.py       # Owner lookup + get_fixed_calendar_organizer()
│       ├── google_sync.py       # Desired-state Calendar sync, called from communication outbox worker
│       ├── views.py             # status/connect/callback/complete/disconnect/refresh
│       └── urls.py              # Routes under /google-calendar/
│
├── assets/
│   ├── static/                  # Source static files
│   ├── templates/mails/         # Email templates
│   └── scripts/                 # Docker entrypoint, Gunicorn config
│
└── docs/                        # ALL documentation lives here
    ├── CODING_RULES.md
    ├── ENVIRONMENT.md
    ├── MEMORY.md                 ← project memory for Claude
    ├── features.md
    ├── associate-roles-rbac.md
    ├── appointments-frontend-api.md
    ├── scheduling.md             # stub → appointments-frontend-api.md
    └── availability.md           # stub → appointments-frontend-api.md
```


### 4.4 Data Model Summary

**Identity & Access**
- `User` (UUID PK, email-based auth) — custom `AUTH_USER_MODEL = 'users.User'`
- `Associate` (1:1 User) + `AssociateRole` (per-center roles with feature ArrayField)
- `GoogleCalendarConnection` (1:1 User) — `google_email`, encrypted tokens, expiry; admin or associate may own the shared calendar. See `docs/google-calendar-integration.md`.
- `AssociateCenterAssignment` — links associate ↔ center with role, is_admin, mode
- `Customer` (1:1 User) + `CustomerProfile` (family members) + `CustomerOnboarding` (health data)
- `Center` + `CenterOperatingHour` + `CenterClosure`

**Scheduling**
- `Schedule` — recurring weekly availability (associate, day_of_week, start/end time, duration, buffer)
- `BlockedPeriod` — one-off unavailability windows (UTC)
- `Appointment` — booked sessions; book lands `confirmed` (no `pending`). Cancel/reschedule from `confirmed` or `checked_in`; `in_progress` is not reversible. No-show from `confirmed` only. Also carries `notes`, `google_event_id`, `google_meet_link` — see `docs/google-calendar-integration.md`.
- `AppointmentHistory` — reschedule window snapshots; `AppointmentAuditLog` — appointment-scoped lifecycle trail

**Services & Inventory**
- `Service` + `ServiceRequirement` — service catalogue per center
- `Composite` + `CompositeService` — service bundles/packages
- `Room` + `RoomSchedule` — physical spaces
- `Equipment` + `EquipmentSchedule` + `EquipmentBooking` + `EquipmentMaintenance`
- `Sequence` — alphanumeric code generator (e.g., center codes, appointment IDs)

### 4.5 API Design Conventions

**Request Context**
- `X-Center-ID` header: Required for all associate-scoped requests.
  `CenterContextMiddleware` populates `request.center_id` and `request.center_assignment`.
- `X-Customer-Profile-ID` header: Populates `request.customer_profile`.

**Authentication**
- JWT Bearer tokens. Access: 1 day. Refresh: 30 days (rotating).
- Custom claims in token: `email`, `phone`, `user_type`.

**Response Format**
```json
// Success
{ "success": true, "detail": "...", "data": { ... } }
// Error
{ "success": false, "detail": "...", "errors": { "field": ["msg"] } }
```

**Permission Hierarchy**
```
IsAuthenticated
├── IsAdminUser               (account_type == 'admin')
├── IsAssociateUser           (account_type == 'associate')
│   ├── BaseAssociateRBACPermission    (validates center assignment)
│   ├── AssociateAdminPermission       (is_admin == True)
│   └── AssociateFeaturePermission     (checks role.features ArrayField)
│       ├── AppointmentFeaturePermission
│       ├── AssociateOnboardingPermission
│       ├── CustomerOnboardingPermission
│       └── PackagesPermission
└── IsCustomerUser            (account_type == 'customer')
```

**URL Namespacing**
- Admin/global routes: `centers/<pk>/...`, `associates/<pk>/...`
- Center-scoped associate routes: `centers/associates/`, `centers/rooms/`, `centers/equipments/`, etc.
- Auth routes: `auth/login/`, `auth/refresh/`, `auth/...`

### 4.6 Scheduling Algorithm

Slot availability is **computed on-demand** — no pre-stored slots.

```
Query: "30-min slots for associate X in room Y, week of Feb 1"

1. EXPAND recurring rules → concrete intervals
   - Center operating hours
   - Associate's Schedule entries
   - Room schedule
   - Equipment schedule (if required)

2. INTERSECT all availability layers

3. SUBTRACT busy periods
   - CenterClosure
   - BlockedPeriod (associate leave, etc.)
   - Existing Appointments
   - EquipmentMaintenance
   - EquipmentBooking

4. SPLIT into fixed-duration slots
```

Key files: `appointments/utils/intervals.py` (pure functions, no Django) and
`appointments/utils/scheduling.py` (DB-aware layer).

### 4.7 Multi-Tenant Design

Data is isolated at the **center** level:
- Associates belong to centers via `AssociateCenterAssignment`
- Services, rooms, equipment are center-scoped
- The `X-Center-ID` request header enforces data isolation at the API layer
- Super Admin → Center Admin → Associates permission hierarchy

---

## 5. Development Workflow

```bash
# Setup
uv venv && source .venv/Scripts/activate  # Windows
uv sync

# Run dev server
uv run manage.py runserver

# Migrations
uv run manage.py makemigrations
uv run manage.py migrate

# Add a package (always use uv, never pip)
uv add <package-name>

# Upgrade all packages to latest
uv sync --upgrade

# Run management commands
uv run manage.py <command>
```

**Settings module:** Set `DJANGO_SETTINGS_MODULE` env var:
- Development: `core.settings.development`
- Staging: `core.settings.staging`
- Production: `core.settings.production`

---

## 6. Deployment

- **Container:** Multi-stage Dockerfile, Python 3.14-slim base, uv for deps, Gunicorn server
- **Orchestration:** AWS ECS with rolling updates (`.github/workflows/deploy-aws.yml`)
- **Database:** AWS RDS PostgreSQL (ap-south-1)
- **Storage:** AWS S3 + CloudFront CDN
- **Email:** AWS SES
- **Security scanning:** PySentry on every push (`.github/workflows/vulnerability-check.yml`)

---

## 7. Documentation Map

| File | Purpose |
|---|---|
| `docs/CODING_RULES.md` | Python/Django coding standards — follow strictly |
| `docs/MEMORY.md` | Project memory for Claude — read before every session |
| `docs/ENVIRONMENT.md` | Environment setup and variable reference |
| `docs/features.md` | Platform feature overview |
| `docs/accounts-architecture.md` | Accounts segmentation — User, Associate, Customer models and rationale |
| `docs/associate-roles-rbac.md` | RBAC design details |
| `docs/scheduling.md` | Scheduling algorithm deep-dive |
| `docs/google-calendar-integration.md` | Google Calendar sync — connect/disconnect flow, identity rules, event sync on book/reschedule/cancel |
| `docs/appointments-frontend-api.md` | Appointments + availability FE API contract (slots, book, lifecycle, exceptions, ops, care teams, calendars, roster/blocks) |
| `docs/scheduling.md` | Stub → `appointments-frontend-api.md` |
| `docs/availability.md` | Stub → `appointments-frontend-api.md` |

---

*Generated: April 2026. Update this file whenever the architecture changes significantly.*