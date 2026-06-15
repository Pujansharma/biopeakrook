# Task: Implement CenterServiceAssignment Bridged Model

**Status:** Planning  
**Created:** 2026-05-11  
**Priority:** High  
**Scope:** Replace Service-Center M2M with bridged model for granular control

---

## Overview

Replace the direct `ManyToManyField` relationship between `Service` and `Center` with an explicit `CenterServiceAssignment` bridged model. This enables:

- Per-center activation/deactivation of services
- Audit trail of service-center assignments (timestamps)
- Better filtering of available services per center
- Atomic bulk operations on service-center relationships

---

## Implementation Steps

### Step 1: Create the Bridged Model

**File:** `services/models.py`

Add the new model to `services/models.py`:

```python
class CenterServiceAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="service_assignments"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "center"], name="unique_service_center"
            )
        ]
        indexes = [
            models.Index(fields=["service", "center"], name="service_center_idx")
        ]

    def __str__(self):
        return f"{self.pk}"
```

Remove from `Service` model:
```python
# DELETE THIS LINE:
centers = models.ManyToManyField("centers.Center", blank=True, related_name="services")
```

**Why:** Explicit bridged model provides better control and audit capabilities than implicit M2M.

---

### Step 2: Create Migration

**File:** `services/migrations/XXXX_create_center_service_assignment.py`

Create a data migration that:

1. Creates the new `CenterServiceAssignment` table
2. Migrates existing Service→Center relationships to the bridged model
3. Removes the M2M table (`Service_centers`)

```bash
uv run manage.py makemigrations --empty services --name create_center_service_assignment
```

In the migration file, populate the bridged model from the old M2M:

```python
def forward(apps, schema_editor):
    Service = apps.get_model('services', 'Service')
    CenterServiceAssignment = apps.get_model('services', 'CenterServiceAssignment')
    
    # Migrate existing M2M relationships
    for service in Service.objects.all():
        centers = service.centers.all()  # Get from old M2M
        assignments = [
            CenterServiceAssignment(service=service, center=center, is_active=True)
            for center in centers
        ]
        CenterServiceAssignment.objects.bulk_create(assignments, ignore_conflicts=True)
```

**Then run:**
```bash
uv run manage.py migrate
```

---

### Step 3: Update Views (`services/views.py`)

#### 3.1: `ServicesView.get_queryset()`

**Current:**
```python
def get_queryset(self):
    filter_kwargs = {}
    prefetch_kwargs = {}
    center_ids = self.request.query_params.getlist("center_id", [])
    if center_ids:
        filter_kwargs["centers__in"] = center_ids
        prefetch_kwargs['pk__in'] = center_ids

    locked_subquery = ProgramService.objects.filter(service=OuterRef('pk'))
    qs = (
        Service.objects.filter(**filter_kwargs)
        .annotate(is_locked=Exists(locked_subquery))
        .prefetch_related(
            Prefetch(
                "centers",
                queryset=Center.objects.filter(**prefetch_kwargs),
            )
        )
        .select_related("created_by")
        .order_by('-created_by')
        .distinct()
    )
    return qs
```

**New:**
```python
def get_queryset(self):
    filter_kwargs = {}
    center_ids = self.request.query_params.getlist("center_id", [])
    if center_ids:
        filter_kwargs["center_assignments__center_id__in"] = center_ids

    locked_subquery = ProgramService.objects.filter(service=OuterRef('pk'))
    qs = (
        Service.objects.filter(**filter_kwargs)
        .annotate(is_locked=Exists(locked_subquery))
        .prefetch_related(
            Prefetch(
                "center_assignments",
                queryset=CenterServiceAssignment.objects.filter(
                    center_id__in=center_ids
                ).select_related("center"),
            )
        )
        .select_related("created_by")
        .order_by('-created_by')
        .distinct()
    )
    return qs
```

#### 3.2: `ServiceDetailView.get_queryset()`

**Current:**
```python
def get_queryset(self):
    qs = (
        Service.objects.filter()
        .prefetch_related("centers")
        .select_related("created_by")
    )
    return qs
```

**New:**
```python
def get_queryset(self):
    qs = (
        Service.objects.filter()
        .prefetch_related(
            Prefetch(
                "center_assignments",
                queryset=CenterServiceAssignment.objects.select_related("center")
            )
        )
        .select_related("created_by")
    )
    return qs
```

#### 3.3: `ServiceAvailableCenters.get_queryset()`

**Current:**
```python
def get_queryset(self):
    search = Q()
    search_params = self.request.query_params.get("search", "").strip()
    if search_params:
        search |= Q(name__istartswith=search_params)
        search |= Q(name__icontains=search_params)

    exists_subquery = Center.objects.filter(
        pk=OuterRef("pk"), services__pk=self.kwargs["pk"]
    )
    qs = Center.objects.filter(search).annotate(exists=Exists(exists_subquery))
    return qs
```

**New:**
```python
def get_queryset(self):
    search = Q()
    search_params = self.request.query_params.get("search", "").strip()
    if search_params:
        search |= Q(name__istartswith=search_params)
        search |= Q(name__icontains=search_params)

    exists_subquery = CenterServiceAssignment.objects.filter(
        center_id=OuterRef("pk"), service_id=self.kwargs["pk"], is_active=True
    )
    qs = Center.objects.filter(search).annotate(exists=Exists(exists_subquery))
    return qs
```

#### 3.4: `ServiceRedeemView.get_queryset()`

**Current:**
```python
def get_queryset(self):
    return ProgramService.objects.select_related(
        "program", "service", "created_by"
    ).prefetch_related("service__centers")
```

**New:**
```python
def get_queryset(self):
    return ProgramService.objects.select_related(
        "program", "service", "created_by"
    ).prefetch_related(
        Prefetch(
            "service__center_assignments",
            queryset=CenterServiceAssignment.objects.filter(is_active=True).select_related("center")
        )
    )
```

**Add import:**

```python
from programs.services import Service, CenterServiceAssignment
```

---

### Step 4: Update Serializers (`services/serializers.py`)

#### 4.1: Update `ServiceSerializer.get_centers()`

**Current:**
```python
def get_centers(self, instance: Service):
    qs = instance.centers.all()[:10]
    return BaseCenterSerializer(qs, many=True, context=self.context).data
```

**New:**
```python
def get_centers(self, instance: Service):
    assignments = instance.center_assignments.select_related("center").filter(is_active=True)[:10]
    centers = [asg.center for asg in assignments]
    return BaseCenterSerializer(centers, many=True, context=self.context).data
```

#### 4.2: Update `ServiceSerializer.add_centers_action()`

**Current:**
```python
def add_centers_action(self, service: Service, add_centers: list) -> None:
    if not add_centers:
        return
    center_ids = [i.get("id") for i in add_centers]
    missing_ids = self.get_invalid_centers(center_ids)
    if missing_ids:
        raise serializers.ValidationError(
            {
                "add_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
            }
        )
    service.centers.add(*center_ids)
```

**New:**

```python
def add_centers_action(self, service: Service, add_centers: list) -> None:
    if not add_centers:
        return
    center_ids = [i.get("id") for i in add_centers]
    missing_ids = self.get_invalid_centers(center_ids)
    if missing_ids:
        raise serializers.ValidationError(
            {
                "add_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
            }
        )

    from programs.services import CenterServiceAssignment

    assignments = [
        CenterServiceAssignment(service=service, center_id=cid, is_active=True)
        for cid in center_ids
    ]
    CenterServiceAssignment.objects.bulk_create(assignments, ignore_conflicts=True)
```

#### 4.3: Update `ServiceSerializer.remove_centers_action()`

**Current:**
```python
def remove_centers_action(self, service: Service, remove_centers: list) -> None:
    if not remove_centers:
        return
    center_ids = [i.get("id") for i in remove_centers]
    missing_ids = self.get_invalid_centers(center_ids)
    if missing_ids:
        raise serializers.ValidationError(
            {
                "remove_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
            }
        )
    service.centers.remove(*center_ids)
```

**New:**

```python
def remove_centers_action(self, service: Service, remove_centers: list) -> None:
    if not remove_centers:
        return
    center_ids = [i.get("id") for i in remove_centers]
    missing_ids = self.get_invalid_centers(center_ids)
    if missing_ids:
        raise serializers.ValidationError(
            {
                "remove_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
            }
        )

    from programs.services import CenterServiceAssignment

    CenterServiceAssignment.objects.filter(
        service=service, center_id__in=center_ids
    ).delete()
```

#### 4.4: Update `TherapyServiceRedeemSerializer.create()`

**Current (Line ~166):**
```python
if not program_service.service.centers.filter(pk=center_id).exists():
    raise serializers.ValidationError(
        {"center_id": "This service is not available at the given center."}
    )
```

**New:**

```python
from programs.services import CenterServiceAssignment

if not CenterServiceAssignment.objects.filter(
        service=program_service.service, center_id=center_id, is_active=True
).exists():
    raise serializers.ValidationError(
        {"center_id": "This service is not available at the given center."}
    )
```

**Add import at top:**

```python
from programs.services import Service, CenterServiceAssignment
```

---

### Step 5: Update Utilities (`services/utils/db.py`)

#### 5.1: Update `update_service_center_count()`

**Current:**
```python
def update_service_center_count(service_id: UUID) -> None:
    subquery = (
        Service.centers.through.objects.filter(service_id=OuterRef("pk"))
        .values("service_id")
        .annotate(cnt=Count("center_id"))
        .values("cnt")
    )
    Service.objects.filter(pk=service_id).update(centers_count=Subquery(subquery))
```

**New:**

```python
def update_service_center_count(service_id: UUID) -> None:
    from programs.services import CenterServiceAssignment

    subquery = (
        CenterServiceAssignment.objects.filter(service_id=OuterRef("pk"), is_active=True)
        .values("service_id")
        .annotate(cnt=Count("center_id"))
        .values("cnt")
    )
    Service.objects.filter(pk=service_id).update(centers_count=Subquery(subquery))
```

---

### Step 6: Update Admin (`services/admin.py`)

**Current:**
```python
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["id", "name"]
    raw_id_fields = ["created_by"]
    filter_horizontal = ["centers"]
    list_per_page = 25
```

**New:**

```python
from django.contrib import admin
from programs.services import Service, CenterServiceAssignment


class CenterServiceAssignmentInline(admin.TabularInline):
    model = CenterServiceAssignment
    extra = 1
    raw_id_fields = ["center"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fields = ["center", "is_active", "created_at", "updated_at"]
    can_delete = True


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["id", "name"]
    raw_id_fields = ["created_by"]
    inlines = [CenterServiceAssignmentInline]
    list_per_page = 25


@admin.register(CenterServiceAssignment)
class CenterServiceAssignmentAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["service", "center", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["service__name", "center__name"]
    raw_id_fields = ["service", "center"]
    list_per_page = 50
```

---

### Step 7: Verify and Test

#### Checklist:

- [ ] Run migrations: `uv run manage.py migrate`
- [ ] Verify M2M data migrated correctly (spot-check in Django shell or admin)
- [ ] Run existing tests: `uv run manage.py test services`
- [ ] Test Service creation with centers via API
- [ ] Test Service update (add/remove centers)
- [ ] Test Service deletion (should be blocked if referenced by ProgramService)
- [ ] Test ServiceAvailableCenters endpoint
- [ ] Test ServiceRedeemView validation
- [ ] Test admin inline for center assignments
- [ ] Verify `centers_count` field updates correctly on add/remove

#### Manual Testing:

```bash
# Create a service with centers
curl -X POST http://localhost:8000/api/services/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Service",
    "add_centers": [{"id": "uuid-1"}, {"id": "uuid-2"}]
  }'

# Verify centers are accessible
curl -X GET http://localhost:8000/api/services/{service-id}/ \
  -H "Authorization: Bearer <token>"

# Remove a center
curl -X PATCH http://localhost:8000/api/services/{service-id}/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "remove_centers": [{"id": "uuid-1"}]
  }'
```

---

## Query Pattern Reference

After implementation, use these patterns:

### Filter Services by Centers

```python
# Active services at specific centers
Service.objects.filter(
    center_assignments__center_id__in=[c1, c2],
    center_assignments__is_active=True
).distinct()
```

### Check Service Availability at Center

```python
# Does this service exist at this center?
CenterServiceAssignment.objects.filter(
    service=service,
    center_id=center_id,
    is_active=True
).exists()
```

### Get All Centers for a Service

```python
# All active centers offering this service
centers = Center.objects.filter(
    service_assignments__service=service,
    service_assignments__is_active=True
).distinct()
```

### Prefetch with Related Center Data

```python
Service.objects.prefetch_related(
    Prefetch(
        "center_assignments",
        queryset=CenterServiceAssignment.objects.filter(is_active=True).select_related("center")
    )
)
```

### Count Active Assignments

```python
# In queryset annotation:
from django.db.models import Count, Q

Service.objects.annotate(
    active_centers_count=Count(
        "center_assignments",
        filter=Q(center_assignments__is_active=True),
        distinct=True
    )
)
```

---

## Rollback Plan

If issues arise:

1. **Revert migration:** `uv run manage.py migrate services 0004` (previous migration)
2. **Restore M2M field** to Service model
3. **Restore old code** in views, serializers, utils
4. **Delete migration file:** `services/migrations/XXXX_create_center_service_assignment.py`

---

## Files Modified

| File | Changes |
|---|---|
| `services/models.py` | Add `CenterServiceAssignment` model, remove `centers` M2M |
| `services/views.py` | Update 4 queryset methods, add import |
| `services/serializers.py` | Update add/remove logic, fix availability check |
| `services/utils/db.py` | Update count subquery |
| `services/admin.py` | Add inline, register bridged model |
| `services/migrations/XXXX_*.py` | New data migration |

---

## References

- Related: Service model filtering, Program service redemption, Service availability
- See also: `docs/models.md` for model overview
- Query patterns: Use `Prefetch` with explicit queryset filters for optimal performance
