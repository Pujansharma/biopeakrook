# Many-to-Many Handling in Serializers

## Overview

This project uses a consistent **add/remove array pattern** for managing M2M relationships
through serializers. It covers two variants:

1. **Pure linking** — a dedicated endpoint whose only job is to add/remove related objects
2. **Combined** — regular model fields (`name`, `is_active`, etc.) alongside `add`/`remove`
   in a single create or update payload

---

## The `IDSerializer` Wrapper

Every add/remove list is typed using a bare `BaseSerializer` subclass with a single `id` field.
This gives clean UUID validation without raw `ListField(child=UUIDField())`.

Define it locally in the serializer file where it is used:

```python
from core.utils.serializers import BaseSerializer

class CenterIDSerializer(BaseSerializer):
    id = serializers.UUIDField(write_only=True)
```

Use it as a typed list field on the parent serializer:

```python
add = CenterIDSerializer(many=True, required=False, write_only=True)
remove = CenterIDSerializer(many=True, required=False, write_only=True)
```

Both `add` and `remove` are always `required=False` — callers can send either or both.

---

## Validation Classmethod

Validate that submitted IDs are legitimate before touching the database.
Define this as a `@classmethod` on the serializer so it can be called for both
the `add` and `remove` paths independently:

```python
@classmethod
def get_invalid_ids(cls, queryset, submitted_ids):
    valid_ids = queryset.filter(pk__in=submitted_ids).values_list('pk', flat=True)
    return set(submitted_ids) - set(valid_ids)
```

Pass the appropriate filtered queryset so validation is scoped correctly:

```python
# Only centers where the service is offered
qs = Center.objects.filter(is_active=True)
invalid = cls.get_invalid_ids(qs, add_ids)
if invalid:
    raise serializers.ValidationError({'add': f'Invalid center IDs: {[str(i) for i in invalid]}'})
```

---

## Variant 1 — Pure Linking (Dedicated Endpoint)

Used when the endpoint's sole responsibility is to manage a relationship.
The serializer has no regular model fields — only `add`, `remove`, and any required
scoping context (e.g., `center_id`).

### Serializer

```python
class ServiceCenterLinkSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(write_only=True)
    add = CenterIDSerializer(many=True, required=False, write_only=True)
    remove = CenterIDSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = Service
        fields = ['center_id', 'add', 'remove']

    @classmethod
    def get_invalid_ids(cls, queryset, submitted_ids):
        valid_ids = queryset.filter(pk__in=submitted_ids).values_list('pk', flat=True)
        return set(submitted_ids) - set(valid_ids)

    def create(self, validated_data):
        add_ids = [i['id'] for i in validated_data.get('add', [])]
        remove_ids = [i['id'] for i in validated_data.get('remove', [])]

        if not add_ids and not remove_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        service = validated_data.pop('service')   # injected by view

        if add_ids:
            invalid = self.get_invalid_ids(Center.objects.all(), add_ids)
            if invalid:
                raise serializers.ValidationError(
                    {'add': f'Invalid IDs: {[str(i) for i in invalid]}'}
                )
            service.centers.add(*add_ids)

        if remove_ids:
            invalid = self.get_invalid_ids(Center.objects.all(), remove_ids)
            if invalid:
                raise serializers.ValidationError(
                    {'remove': f'Invalid IDs: {[str(i) for i in invalid]}'}
                )
            service.centers.remove(*remove_ids)

        return 1  # sentinel — no meaningful object to return
```

### View

Inject the object into `perform_create` so it stays out of the request payload:

```python
class ServiceLinkCentersView(BaseCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ServiceCenterLinkSerializer

    def perform_create(self, serializer):
        service = get_object_or_404(Service, pk=self.kwargs['pk'])
        serializer.save(service=service)
```

### When to use plain M2M `.add()` / `.remove()` vs `bulk_create`

| Relationship type | Method |
|---|---|
| Plain M2M (no through model) | `.add(*ids)` / `.remove(*ids)` |
| Through model with extra fields | `bulk_create` with `update_conflicts=True` + `.delete()` |

For plain M2M, Django handles the junction table. Use `.add()` and `.remove()` directly.

For through models with extra fields (e.g., `created_by`, `sessions_allotted`):

```python
assignments = [
    ProgramService(program=program, service_id=sid, created_by=created_by)
    for sid in add_ids
]
ProgramService.objects.bulk_create(
    assignments,
    update_conflicts=True,
    unique_fields=['program', 'service'],
    update_fields=['created_by'],
)

ProgramService.objects.filter(
    program=program, service_id__in=remove_ids
).delete()
```

`update_conflicts=True` makes the add idempotent — submitting the same IDs twice
updates the extra fields rather than raising an integrity error.

---

## Variant 2 — Combined (Create / Update with M2M in Same Payload)

Used when the endpoint manages a model's own fields alongside its M2M relationships
in the same request. Example: creating a `Service` with its `name` and its `centers`
in one call.

### Request shape

```json
// POST /services/
{
    "name": "Physiotherapy",
    "add": [{"id": "<center_uuid>"}, {"id": "<center_uuid>"}]
}

// PATCH /services/<pk>/
{
    "name": "Updated Name",
    "add": [{"id": "<center_uuid>"}],
    "remove": [{"id": "<center_uuid>"}]
}
```

### Serializer

```python
class ServiceSerializer(BaseModelSerializer):
    add = CenterIDSerializer(many=True, required=False, write_only=True)
    remove = CenterIDSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = Service
        fields = ['id', 'name', 'is_active', 'add', 'remove', 'created_at']
        read_only_fields = ['id', 'created_at']

    @classmethod
    def get_invalid_ids(cls, queryset, submitted_ids):
        valid_ids = queryset.filter(pk__in=submitted_ids).values_list('pk', flat=True)
        return set(submitted_ids) - set(valid_ids)

    def _handle_centers(self, service, add_ids, remove_ids):
        center_qs = Center.objects.all()

        if add_ids:
            invalid = self.get_invalid_ids(center_qs, add_ids)
            if invalid:
                raise serializers.ValidationError(
                    {'add': f'Invalid center IDs: {[str(i) for i in invalid]}'}
                )
            service.centers.add(*add_ids)

        if remove_ids:
            invalid = self.get_invalid_ids(center_qs, remove_ids)
            if invalid:
                raise serializers.ValidationError(
                    {'remove': f'Invalid center IDs: {[str(i) for i in invalid]}'}
                )
            service.centers.remove(*remove_ids)

    def create(self, validated_data):
        add_ids = [i['id'] for i in validated_data.pop('add', [])]
        remove_ids = [i['id'] for i in validated_data.pop('remove', [])]

        with transaction.atomic():
            service = Service.objects.create(**validated_data)
            self._handle_centers(service, add_ids, remove_ids)

        return service

    def update(self, instance, validated_data):
        add_ids = [i['id'] for i in validated_data.pop('add', [])]
        remove_ids = [i['id'] for i in validated_data.pop('remove', [])]

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            self._handle_centers(instance, add_ids, remove_ids)

        return instance
```

Key points:
- Pop `add` and `remove` from `validated_data` **before** calling `super().update()` or
  `Model.objects.create()` — they are not model fields and will cause an error if left in.
- Extract the M2M logic into a private `_handle_centers` method so both `create` and
  `update` share the same validation and mutation path.
- Wrap in `transaction.atomic()` so a validation error on the M2M step rolls back the
  main object write.

---

## Rules Summary

| Rule | Reason |
|---|---|
| Always `required=False` on `add`/`remove` | Callers may send only one direction |
| Validate IDs before any DB write | Fail fast before partial mutation |
| Pop `add`/`remove` before `super().update()` | They are not model fields |
| Use `transaction.atomic()` in combined variant | M2M failure must roll back the main write |
| Use `bulk_create` with `update_conflicts=True` for through models | Idempotent — safe to call twice |
| Use plain `.add()` / `.remove()` for plain M2M | Simpler, Django handles the junction |
| Return sentinel `1` from pure-linking `create` | No meaningful instance to return |
| Extract M2M logic into `_handle_*` method | Shared by `create` and `update` without duplication |