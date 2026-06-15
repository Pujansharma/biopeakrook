# Program, Services, Packages, and Provider ERD

## Purpose

This document explains the high level ERD for Biopeak Nexus around service definition, provider-backed assessment products, client programs, service redemption, and composite programs.

The model is a strong fit for Biopeak because it separates four concerns that must evolve independently:

- who can log in and act in the platform
- where Biopeak work happens
- what Biopeak offers as reusable service definitions
- what a specific client has been assigned and can redeem

That separation is what makes the structure scalable. A service can be defined once, made available only at selected centers, assigned to many clients with different quantities, redeemed over time, and audited without duplicating catalog records or losing history.

## Existing Project Model Mapping

The ERD uses business names such as `Client`, `Program`, `Service`, `Provider`, and `CompositeProgram`. Keep the ERD naming as `Client`. In the current Django implementation, `Client` maps to the existing customer profile model because programs and care delivery attach to that care recipient record. The table below maps ERD concepts to the closest project model or intended model name so the document supports the ERD structure.

| ERD concept | Project model or intended model | Notes |
|---|---|---|
| User | `accounts.users.User` | UUID7 primary key, optional unique email, optional unique phone, profile fields, password support. |
| Admin | `accounts.admins.Admin` | One-to-one with `User`; no center foreign key, which correctly represents platform-level access. |
| Associate | `accounts.associates.Associate` | One-to-one with `User`; staff identity independent of center assignment. |
| AssociateCenter | `accounts.associates.AssociateCenterAssignment` | Links associate to center with role, mode, `is_admin`, `is_care_staff`, and primary center flag. |
| Center | `accounts.centers.Center` | Stores center identity, address, mode, status, contact data, and counts. |
| Client | `accounts.customers.CustomerProfile` | The ERD name is `Client`. In code, `Customer` remains the phone-login owner, while the client record is implemented by the customer profile model. |
| ClientCenter | `accounts.customers.CustomerCenterAssignment` | Links client to center with a single primary center constraint. |
| Client care staff | `accounts.customers.CustomerAssociateAssignment` | Links client, associate, and center, which supports center-specific care relationships. |
| Service | `programs.services.Service` | Service carries the reusable service definition, including type and product relationships in the ERD. |
| Service available centers | `programs.services.CenterServiceAssignment` | Explicit bridge model replaces direct service-center many-to-many and is the correct design for center availability. |
| Provider | `products.Provider` | Stores provider callback, required fields, fetch fields, API enabled flag, contact details, and code. |
| Provider API config | `products.ProviderAPI` | One-to-one provider API credential/config payload. This is an implementation improvement over storing all API data directly on provider. |
| Product | `products.Product` | Belongs to provider, has product callback, data, tags, sample file, and generated code. |
| Program | `programs.Program` | Assigned to a client, issued at a center, can be redeemed at selected centers, stores program type, price, expiry, counts, and cancellation state. |
| ProgramService | `programs.ProgramService` | Links assigned program to service with quantity as `sessions_count`, usage as `sessions_used`, QR redeem code, and cancellation state. |
| Redemption history | `programs.RedemptionHistory` | Immutable redemption/cancellation event log per program service and center. |
| Composite definition | `CompositeProgramDefinition` | Defines the reusable composite structure described in the ERD. |
| Composite definition service | `CompositeDefinitionService` | Defines services and quantities in the reusable composite definition. |
| Composite program assignment | `CompositeProgram` | Assigns a composite definition to a client and snapshots the assignment context. |
| Composite program service | `CompositeProgramService` | Stores assigned composite services, quantities, and usage state per client assignment. |

## Identity and Access Model

The ERD starts with `User` because authentication should be independent of business role. This is exactly right for Biopeak.

`User` is the login record. It stores email, phone, password hash, active status, and profile fields. Different portals and login methods can be layered on top:

- admins and associates can authenticate using email and password
- clients can authenticate using phone and OTP
- phone and email can both remain unique without forcing every role to use both

`Admin`, `Associate`, and `Customer` are one-to-one extensions of `User`. This keeps authentication normalized and lets the platform answer a simple question: "who is logging in?" After authentication, the related profile answers the next question: "what can this user do?"

This is especially important because one person can act in different contexts. An admin can access all centers, an associate can work at multiple centers, and a client portal user may own multiple client records or family profiles.

## Admins

Admins are intentionally not linked to a center. That is correct because their authority is platform-wide.

Example:

- A Biopeak operations admin logs in with email and password.
- They can create centers such as Indiranagar and Grace Towers.
- They can define services, providers, products, and programs.
- They can access all center data subject to platform rules.

If admins were linked directly to centers, every platform-level action would require exceptions. The ERD avoids that by keeping `Admin` separate from `Center`.

## Associates and Center Assignments

The associate design is strongest when role flags live on the center assignment rather than only on the associate.

The current project already does this through `AssociateCenterAssignment`:

- `associate`
- `center`
- `role`
- `mode`
- `is_primary`
- `is_admin`
- `is_care_staff`

This is better than a single global `Associate.is_admin` or `Associate.is_care_team` flag because an associate's responsibility can change by center.

Example:

| Associate | Center | Admin? | Care staff? | Meaning |
|---|---|---:|---:|---|
| Dr. Meera | Indiranagar | Yes | Yes | Can manage center operations and deliver care. |
| Dr. Meera | Grace Towers | No | Yes | Can deliver care but cannot administer the center. |
| Raj | Indiranagar | Yes | No | Can manage front desk and redemptions but is not clinical care staff. |

This matches the real Biopeak operating model: people are not simply "admins" or "care staff" globally. They are assigned responsibilities at a center.

## Clients, Profiles, Centers, and Care Staff

The ERD's `Client` is the domain name for the care recipient. This keeps the diagram simple while still matching the important runtime behavior: programs and care delivery belong to the client.

In the current project:

- `Customer` is the phone-login account in the current implementation.
- `Client` is the care recipient in the ERD.
- `ClientCenter` links a client to centers.
- Client care staff assignment links a client to care staff at a specific center.

This is the correct structure because the person who logs in may not always be the only care recipient. A customer account can own multiple client records, such as self, spouse, parent, or child. For the ERD, that care recipient is named `Client`.

Example:

- A phone number belongs to Rohan.
- Rohan logs in to the client portal.
- Rohan has two profiles: "Rohan" and "Rohan's father".
- An assessment program may be assigned to Rohan's father, while a therapy program may be assigned to Rohan.

The ERD's `ClientCenter` join table is also correct because a client can be connected to more than one center, but exactly one can be primary.

## Services

A service is the smallest reusable unit of Biopeak delivery. It should represent the definition of the action, not a specific client's usage.

Examples:

- IR Sauna
- Gut Healing
- Doctor Consultation
- Blood Collection
- Genomic Health Insights
- NutriDNA

The ERD correctly gives service these responsibilities:

- name
- type
- available centers
- assessment products, when applicable

The current project already implements the service catalog and center availability bridge:

- `Service` stores the global catalog record.
- `CenterServiceAssignment` links a service to each center where it is available.

This bridge model is the right design because it can later carry center-specific operational settings without changing the service itself. For example, IR Sauna can be a single service, while availability, active status, room requirements, pricing overrides, or capacity rules can vary by center.

## Providers and Products

Provider and product modeling is essential only for assessment services. Therapy and consultation services can usually be redeemed or scheduled internally, while assessments often require an external company, an API flow, a report, or a callback function.

The ERD's provider design is correct because it separates:

- the external company
- the provider-level API configuration
- the products that company offers
- the internal callback functions that know how to execute or fetch product-specific data

The current project implements this through:

- `Provider`
- `ProviderAPI`
- `Product`

Example provider setup:

1. Admin creates provider `Healthians`.
2. Admin selects provider callback `healthians`.
3. Admin marks API enabled only after required API fields are configured.
4. Admin defines required fields such as customer phone, address, and appointment date.
5. Admin defines fetch fields such as report URL, lab order ID, and sample status.
6. Admin adds product `Blood Collection` with product callback `blood`.

Example genomics provider setup:

1. Admin creates provider `Strand Genomics`.
2. Admin selects provider callback `strand`.
3. Admin configures required fields such as sample barcode and consent reference.
4. Admin adds product `Genomic Health Insights`.
5. Admin adds product `NutriDNA`.
6. Each product selects its own callback function, so the UI and backend action can differ by product.

This is the right shape because provider-level behavior and product-level behavior are not the same. A provider API may handle authentication, field requirements, and fetch rules, while the product callback determines the exact action for a specific product.

## Assessment Services

Assessment services should connect one Biopeak-facing service to one or more provider products.

Example:

- Provider: Strand Genomics
- Products: Genomic Health Insights, NutriDNA
- Service: DNA Assessment
- Service type: assessment
- Service products: Genomic Health Insights and NutriDNA
- Available centers: Indiranagar and Grace Towers

When a client receives an assessment program containing `DNA Assessment`, the assessment UI can look at the linked products and show product-specific actions:

- collect required fields
- create provider order
- upload sample data
- fetch status
- fetch report
- display result artifacts

This keeps the UI dynamic without hardcoding provider behavior into every program. The service tells the program what was assigned; the product tells the assessment workflow what action is available.

## Programs

A program is a client-specific assignment of services and quantities.

This is the most important distinction in the ERD:

- `Service` is the reusable definition.
- `Program` is the client assignment.
- `ProgramService` is the assigned service line item with quantity and usage.

The current project implements quantity as `ProgramService.sessions_count` and usage as `ProgramService.sessions_used`. The ERD's `quantity` field maps directly to this.

Example therapy program:

| Field | Value |
|---|---|
| Client | Ananya Rao |
| Issuing center | Indiranagar |
| Redeemable centers | Indiranagar |
| Program type | therapy |
| Services | IR Sauna, Gut Healing |
| IR Sauna quantity | 6 |
| Gut Healing quantity | 4 |

This creates:

- one `Program`
- two `ProgramService` rows
- one redeem code per service line
- aggregate counts on the program

The program is not redefining IR Sauna or Gut Healing. It is only saying that Ananya has been granted a specific number of sessions for each.

## Redemption Flow

The redemption flow described in the ERD is exactly the right operational model for therapy-style services.

Example:

1. Client visits Indiranagar.
2. Client shows the QR code for IR Sauna.
3. Associate scans the code.
4. Backend finds the `ProgramService` by redeem code.
5. Backend verifies that the service is active.
6. Backend verifies that the program has not expired.
7. Backend verifies that the selected center offers that service through `CenterServiceAssignment`.
8. Backend checks remaining quantity.
9. Backend increments `sessions_used`.
10. Backend creates a `RedemptionHistory` row.

The history record is critical. It gives Biopeak an audit trail for:

- when the service was redeemed
- where it was redeemed
- who redeemed it
- how many sessions were consumed
- whether the event was redemption or cancellation

This is why the ERD should keep redemption history separate from the current count fields. Counts are current state; history is the source of operational truth.

## Assessment Program Flow

Assessment programs use the same assignment structure, but their post-assignment action differs.

Example:

| Step | Action |
|---|---|
| 1 | Admin selects client `Ananya Rao`. |
| 2 | Admin selects redeemable center `Indiranagar`. |
| 3 | Admin adds assessment service `DNA Assessment`. |
| 4 | Service is linked to products `Genomic Health Insights` and `NutriDNA`. |
| 5 | Program is created with one or more service quantities. |
| 6 | Assessment UI reads the linked products and provider callbacks. |
| 7 | UI shows actions such as collect sample details, create external order, fetch status, and fetch report. |

The key insight is that assessment behavior should come from provider/product configuration, not from a special hardcoded program type.

That makes the model extensible:

- Healthians can power blood collection.
- Strand Genomics can power genomics reports.
- Evo can power metabolic or other assessment products.
- Biopeak can add new providers without rewriting the entire program model.

## Composite Programs

Composite programs are different from normal programs because they begin as reusable definitions or bundles, then become client-specific assignments.

A composite can include mixed service types:

- assessment service
- therapy service
- consultation service

Example composite definition:

| Composite definition | Biopeak Metabolic Reset |
|---|---|
| Available centers | Indiranagar, Grace Towers |
| Universal? | No |

Definition services:

| Service | Type | Quantity |
|---|---|---:|
| Blood Collection | assessment | 1 |
| IR Sauna | therapy | 6 |
| Gut Healing | therapy | 4 |
| Doctor Consultation | consultation | 2 |

When assigned to a client, the system should create a client-specific composite program:

| Composite program | Value |
|---|---|
| Client | Ananya Rao |
| Composite definition | Biopeak Metabolic Reset |
| Redeemable center | Indiranagar |

Then it should create assigned composite service rows:

| Assigned service | Quantity | Runtime behavior |
|---|---:|---|
| Blood Collection | 1 | Provider/product assessment action |
| IR Sauna | 6 | QR/session redemption |
| Gut Healing | 4 | QR/session redemption |
| Doctor Consultation | 2 | Appointment or consultation workflow |

This is why the ERD separates `CompositeProgramDefinition` from `CompositeProgram`. Definitions are reusable templates. Assigned composite programs are client-specific and should preserve what was granted at the time of assignment.

The composite structure should follow the ERD rather than be treated as an extension of the current service program model.

The target structure should include:

- `CompositeProgramDefinition`
- `CompositeDefinitionService`
- `CompositeProgram`
- `CompositeProgramService`

This prevents old client assignments from changing unexpectedly if an admin later edits the composite definition.

## Why This Structure Is a Perfect Fit

The ERD is a perfect fit for this project scenario because it models definitions, assignments, actors, centers, external integrations, and usage events as separate concepts.

### 1. It supports mixed authentication without role confusion

The `User` table handles identity. `Admin`, `Associate`, and `Customer` handle business role. This supports email/password for staff and phone/OTP for clients without bending one account model around every portal.

### 2. It respects center-specific responsibilities

Associates are not globally admins or care staff. Their permissions depend on the center. `AssociateCenterAssignment` captures that reality cleanly.

### 3. It models the care recipient accurately

Programs belong to the client, not merely the login account. That supports family profiles and dependent care, which is common in healthcare and wellness platforms.

### 4. It keeps service catalog records reusable

Services are definitions. They do not store client-specific quantity or usage. That means Biopeak can report on "IR Sauna" across all programs and centers without cleaning up duplicated service rows.

### 5. It lets service availability vary by center

`CenterServiceAssignment` means a service can exist globally but be available only at selected centers. This matches examples like IR Sauna at Indiranagar or Gut Healing at Grace Towers.

### 6. It isolates provider integration complexity

Assessment services often need provider APIs, required fields, fetch fields, product callbacks, sample files, and reports. The provider/product model contains that complexity without polluting therapy or consultation services.

### 7. It gives programs stable assigned quantities

`ProgramService` is where quantity belongs. A client can receive 6 IR Sauna sessions while another receives 10, even though both use the same underlying service.

### 8. It gives redemption a real audit trail

`RedemptionHistory` records each usage event. Counts can be recomputed, support dashboards, and speed up queries, but the history preserves what actually happened.

### 9. It supports composites without losing flexibility

Composite definitions make reusable packages. Composite assignments make client-specific packages. This allows mixed assessment, therapy, and consultation plans without forcing every package to behave like a single service.

### 10. It stays extensible

New providers, products, service types, centers, care staff assignments, and program types can be added without redesigning the core identity or redemption model.

## ERD Structural Summary

The ERD structure contains these main model groups:

| Model group | ERD structures | Purpose |
|---|---|---|
| Identity | `User`, `Admin`, `Associate`, `Client` | Separates authentication from business roles and client care records. |
| Center assignment | `Center`, `AssociateCenter`, `ClientCenter`, client care staff assignment | Represents where work happens and which people are linked to each center. |
| Service catalog | `Service`, service available centers, service products | Defines Biopeak services, their type, where they are available, and which provider products they cover. |
| Provider catalog | `Provider`, `Product`, provider API configuration | Represents external assessment providers, their API requirements, and their products. |
| Program assignment | `Program`, `ProgramService`, `RedemptionHistory` | Represents services granted to a client, their quantities, usage state, and audit history. |
| Composite structure | `CompositeProgramDefinition`, `CompositeDefinitionService`, `CompositeProgram`, `CompositeProgramService` | Represents reusable mixed-service composite definitions and client-specific composite assignments. |

## Final Position

The ERD is not just a diagram of tables. It is a good domain boundary for Biopeak Nexus.

It correctly treats service setup, provider setup, program assignment, composite packaging, and redemption history as separate layers. That makes the system easier to extend, easier to audit, and easier to operate across multiple centers.
