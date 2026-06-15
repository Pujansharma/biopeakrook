# Program Management

## Overview

A **Program** is a composable container of services assigned to a customer. It represents a structured
engagement, such as a therapy plan, with a defined set of services the customer can redeem across
one or more centers.

Programs are issued at a single center (`center` FK) but can be redeemed at multiple centers
(`redeemable_centers` M2M). Each program has a type (for example, `therapy`), and the type-specific
model carries a `OneToOneField` back to `Program`.

---

## Architecture

```
services/
├── models.py                        # Service (global catalog, center-assigned via M2M)
└── programs/
    ├── models.py                    # Program, ProgramService, TherapyProgram
    └── utils/
        └── constants.py            # ProgramType
```

---

## Models

### Service

Global service catalog. A service can be assigned to multiple centers via the `centers` M2M.
Pricing is not stored here — it lives on `Program`.

| Field | Type | Purpose |
|---|---|---|
| `name` | CharField | Service display name |
| `centers` | M2M(Center) | Centers where this service is offered |
| `created_by` | FK(User, nullable) | Associate who created this service |

### Program

The core customer-facing container. One program per engagement.

| Field | Type | Purpose |
|---|---|---|
| `customer` | FK(Customer) | The customer this program belongs to |
| `center` | FK(Center) | Issuing center (where the program was created/sold) |
| `program_type` | CharField(ProgramType) | Discriminator for type-specific model |
| `notes` | TextField (nullable) | Internal notes |
| `expires_at` | DateField (nullable) | Program expiry date |
| `is_complimentary` | BooleanField | Whether this is a complimentary program (default: True) |
| `price` | DecimalField (nullable) | Program-level price |
| `sessions_count` | PositiveIntegerField | Total sessions allotted in this program |
| `sessions_used` | PositiveIntegerField | Sessions consumed so far (default: 0) |
| `redeemable_centers` | M2M(Center) | Centers where this program can be redeemed |

### ProgramService

Links a program to a service. FK is to the global `Service`.
At booking time the scheduling engine resolves the correct center context from the
customer's chosen redemption center.

| Field | Type | Purpose |
|---|---|---|
| `program` | FK(Program) | Parent program |
| `service` | FK(Service) | Service included in this program |
| `created_by` | FK(User, nullable) | Associate who added this service to the program |

Constraint: `unique_together: (program, service)`

### TherapyProgram

Type-specific extension for therapy programs. One-to-one with `Program`
(enforced by `OneToOneField`). A program cannot have more than one type object.

| Field | Type | Purpose |
|---|---|---|
| `program` | OneToOneField(Program) | Parent program |

Add therapy-specific fields here as the domain grows.

---

## Constants

### ProgramType

Defined in `programs/utils/constants.py`.

| Constant | Value | Description |
|---|---|---|
| `THERAPY` | `therapy` | Therapy program |

Add new types here as the platform expands. Each new type requires a corresponding
type-specific model with a `OneToOneField` back to `Program`.

---

## Type Object Pattern

Each `program_type` value corresponds to exactly one type-specific model:

```
Program (program_type='therapy')
  └── TherapyProgram (OneToOne -> Program)
        └── therapy-specific fields

Program (program_type='consultation')        <- future
  └── ConsultationProgram (OneToOne → Program)
```

The `program_type` field is the discriminator — it tells you which related object to access
without querying all type tables. A program cannot have more than one type object.

---

## Frontend Flow

```
1. Associate selects redeemable centers for the program
   → filtered from the customer's associated centers

2. Services are shown based on selected centers
   → Service.objects.filter(centers__in=selected_centers).distinct()

3. Associate picks services for the program
   → ProgramService rows created (FK to global Service)

4. Program is saved with issuing center + redeemable centers + services
```

Validation that selected services are available at the chosen redeemable centers
is handled in the serializer `create` method, not at the model level.

---

## Booking Flow (Redemption)

When a customer books a session under a program service:

```
1. Customer picks a redemption center (from program.redeemable_centers)

2. Scheduling engine verifies the service is offered at that center:
   program_service.service.centers.filter(pk=chosen_center.pk).exists()

3. Availability is computed for that (service, center) combination

4. On booking: program.sessions_used is incremented
```
