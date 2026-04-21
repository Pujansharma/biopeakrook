# Base Models

All models in Biopeak Nexus extend one of two abstract base classes defined in `core/utils/models.py`.

---

## `BaseModel`

```python
class BaseModel(models.Model):
    is_active   = BooleanField(default=True)
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)
    objects     = BaseModelManager()

    class Meta:
        abstract = True
```

**Fields**

| Field | Type | Notes |
|---|---|---|
| `is_active` | `BooleanField` | Soft-active flag. Default `True`. Not a soft-delete — just a status toggle. |
| `created_at` | `DateTimeField` | Set once on insert (`auto_now_add`). |
| `updated_at` | `DateTimeField` | Updated on every save (`auto_now`). |

**Manager — `BaseModelManager` / `BaseQuerySet`**

Adds convenience query methods:

| Method | Behaviour |
|---|---|
| `filter_active(**kwargs)` | Injects `is_active=True` into the filter |
| `get_active(**kwargs)` | `get()` with `is_active=True` |
| `get_active_by_pk(pk)` | `get(pk=pk, is_active=True)` |
| `filter_inactive(**kwargs)` | Injects `is_active=False` into the filter |

**Primary key** — Django default auto-int `id` unless overridden by `BaseUUIDModel` or a model-level `primary_key=True` field.

---

## `BaseUUIDModel`

```python
class BaseUUIDModel(BaseModel):
    id = UUIDField(default=uuid.uuid7, primary_key=True, db_index=True, editable=False)

    class Meta:
        abstract = True
```

Extends `BaseModel` with a UUID7 primary key.

| Field | Notes |
|---|---|
| `id` | UUID7 — time-ordered, globally unique. Better index performance than UUID4. |

Use `BaseUUIDModel` for all new models unless a natural FK is more appropriate as the PK (e.g. `Admin`, where `user` is `primary_key=True`).

---

## PK design note

Some models use a OneToOneField as the PK instead of `BaseUUIDModel`:

```python
# Admin — pk IS user_id (a UUID from the User model)
user = OneToOneField(User, primary_key=True, ...)
```

In these cases `model.pk == model.user_id`, and the UUID identity comes from the related `User` object. The serializer exposes it as `id = UUIDField(source='user.id', read_only=True)`.
