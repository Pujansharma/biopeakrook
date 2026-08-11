# Frontend API PRD: Customer Center Assignment

## GET Customer Center Assignment

### URL

```text
<baseURL>/profiles/center-assignments/<assignment_uuid>/
```

### Request Payload

```json
null
```

### Response

```json
{
  "detail": "Details.",
  "data": {
    "id": "019d0bb7-38ab-7ef1-9724-87f8714228a9",
    "center": {
      "id": "019d0bb7-386d-77c2-a616-78c74dde7576",
      "code": "CTR001",
      "name": "Biopeak Wellness Center",
      "image": "https://example.com/media/centers/biopeak.png",
      "address": "12 Wellness Avenue",
      "address_line_1": "12 Wellness Avenue",
      "address_line_2": "Near Central Park",
      "city": "Bengaluru",
      "state": "Karnataka",
      "country": "India",
      "pincode": "560001",
      "staff_count": 12,
      "inactive_staff_count": 1,
      "customer_count": 150,
      "inactive_customer_count": 5,
      "is_active": true,
      "created_at": "2026-07-31T10:00:00+05:30",
      "updated_at": "2026-07-31T10:00:00+05:30"
    },
    "is_primary": true,
    "created_at": "2026-07-31T10:00:00+05:30",
    "created_by": {
      "id": "019d0bb7-3893-7f16-8c4c-c4408459fb7c",
      "email": "admin@example.com",
      "first_name": "Biopeak",
      "last_name": "Admin",
      "image": null,
      "last_login": "2026-07-31T09:00:00+05:30"
    }
  }
}
```

## PUT Customer Center Assignment

### URL

```text
<baseURL>/profiles/center-assignments/<assignment_uuid>/
```

### Request Payload

```json
{
  "is_primary": true
}
```

### Response

```json
{
  "detail": "Modified successfully.",
  "data": {
    "id": "019d0bb7-38ab-7ef1-9724-87f8714228a9",
    "center": {
      "id": "019d0bb7-386d-77c2-a616-78c74dde7576",
      "code": "CTR001",
      "name": "Biopeak Wellness Center",
      "image": "https://example.com/media/centers/biopeak.png",
      "address": "12 Wellness Avenue",
      "address_line_1": "12 Wellness Avenue",
      "address_line_2": "Near Central Park",
      "city": "Bengaluru",
      "state": "Karnataka",
      "country": "India",
      "pincode": "560001",
      "staff_count": 12,
      "inactive_staff_count": 1,
      "customer_count": 150,
      "inactive_customer_count": 5,
      "is_active": true,
      "created_at": "2026-07-31T10:00:00+05:30",
      "updated_at": "2026-07-31T10:00:00+05:30"
    },
    "is_primary": true,
    "created_at": "2026-07-31T10:00:00+05:30",
    "created_by": {
      "id": "019d0bb7-3893-7f16-8c4c-c4408459fb7c",
      "email": "admin@example.com",
      "first_name": "Biopeak",
      "last_name": "Admin",
      "image": null,
      "last_login": "2026-07-31T09:00:00+05:30"
    }
  }
}
```

## PATCH Customer Center Assignment

### URL

```text
<baseURL>/profiles/center-assignments/<assignment_uuid>/
```

### Request Payload

```json
{
  "is_primary": true
}
```

or

```json
{
  "is_primary": false
}
```

### Response

```json
{
  "detail": "Updated successfully.",
  "data": {
    "id": "019d0bb7-38ab-7ef1-9724-87f8714228a9",
    "center": {
      "id": "019d0bb7-386d-77c2-a616-78c74dde7576",
      "code": "CTR001",
      "name": "Biopeak Wellness Center",
      "image": "https://example.com/media/centers/biopeak.png",
      "address": "12 Wellness Avenue",
      "address_line_1": "12 Wellness Avenue",
      "address_line_2": "Near Central Park",
      "city": "Bengaluru",
      "state": "Karnataka",
      "country": "India",
      "pincode": "560001",
      "staff_count": 12,
      "inactive_staff_count": 1,
      "customer_count": 150,
      "inactive_customer_count": 5,
      "is_active": true,
      "created_at": "2026-07-31T10:00:00+05:30",
      "updated_at": "2026-07-31T10:00:00+05:30"
    },
    "is_primary": true,
    "created_at": "2026-07-31T10:00:00+05:30",
    "created_by": {
      "id": "019d0bb7-3893-7f16-8c4c-c4408459fb7c",
      "email": "admin@example.com",
      "first_name": "Biopeak",
      "last_name": "Admin",
      "image": null,
      "last_login": "2026-07-31T09:00:00+05:30"
    }
  }
}
```

### Primary Unassignment Response

```json
{
  "detail": "Primary center cannot be unassigned without setting another center as home center"
}
```

## DELETE Customer Center Assignment

### URL

```text
<baseURL>/profiles/center-assignments/<assignment_uuid>/
```

### Request Payload

```json
null
```

### Response

```json
{
  "detail": "Deleted successfully."
}
```

### Primary Assignment Response

```json
{
  "detail": "The primary center assignment cannot be deleted."
}
```
