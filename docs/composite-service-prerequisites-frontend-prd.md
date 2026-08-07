# Frontend API PRD: Composite Service Prerequisites

## PUT Composite Service Prerequisite

### URL

```text
<baseURL>/programs/composites/services/019c2c8e-38ab-7ef1-9724-87f8714228a9/prerequisites/
```

### Request Payload

```json
{
  "add_related_services": [
    {
      "id": "019c2c8e-386d-77c2-a616-78c74dde7576"
    },
    {
      "id": "019c2c8e-3893-7f16-8c4c-c4408459fb7c"
    }
  ],
  "remove_related_services": [],
  "condition": "require_any"
}
```

### Response

```json
{
  "detail": "Modified successfully.",
  "data": {
    "related_services_count": 2,
    "related_services": [
      {
        "template_service_id": "019c2c8e-386d-77c2-a616-78c74dde7576",
        "name": "Blood Diagnostics",
        "service_category": "Assessment",
        "service_category_code": "assessment"
      },
      {
        "template_service_id": "019c2c8e-3893-7f16-8c4c-c4408459fb7c",
        "name": "DXA Scan",
        "service_category": "Assessment",
        "service_category_code": "assessment"
      }
    ],
    "condition": "Any one required",
    "condition_code": "require_any"
  }
}
```

## GET Linked Prerequisite Services

### URL

```text
<baseURL>/programs/composites/prerequisites/019c2c8e-38ab-7ef1-9724-87f8714228a9/prerequisite-services/
```

### Request Payload

```json
null
```

### Response

```json
{
  "detail": "All data.",
  "count": 2,
  "next": null,
  "previous": null,
  "data": [
    {
      "template_service_id": "019c2c8e-386d-77c2-a616-78c74dde7576",
      "name": "Blood Diagnostics",
      "service_category": "Assessment",
      "service_category_code": "assessment"
    },
    {
      "template_service_id": "019c2c8e-3893-7f16-8c4c-c4408459fb7c",
      "name": "DXA Scan",
      "service_category": "Assessment",
      "service_category_code": "assessment"
    }
  ]
}
```

## GET Available Prerequisite Services

### URL

```text
<baseURL>/programs/composites/prerequisites/019c2c8e-38ab-7ef1-9724-87f8714228a9/available-prerequisite-services/
```

### Request Payload

```json
null
```

### Response

```json
{
  "detail": "All data.",
  "count": 2,
  "next": null,
  "previous": null,
  "data": [
    {
      "template_service_id": "019c2c8e-386d-77c2-a616-78c74dde7576",
      "name": "Blood Diagnostics",
      "service_category": "Assessment",
      "service_category_code": "assessment",
      "is_exists": true
    },
    {
      "template_service_id": "019c2c8e-3893-7f16-8c4c-c4408459fb7c",
      "name": "DXA Scan",
      "service_category": "Assessment",
      "service_category_code": "assessment",
      "is_exists": false
    }
  ]
}
```
