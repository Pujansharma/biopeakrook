# Frontend API PRD: Programs → Composite Templates → Composite Programs

## Composite Templates

### GET Composite Templates

#### URL

```text
<baseURL>/programs/composites/templates/?page=<page>&limit=<limit>
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<uuid>",
      "code": "<string>",
      "name": "<string|null>",
      "description": "<string|null>",
      "services": [
        {
          "id": "<service_uuid>",
          "name": "<string>",
          "quantity": "<integer>",
          "is_global": "<boolean>",
          "service_category": "<string>",
          "service_category_code": "<therapy|assessment|consultation>",
          "image": "<url|null>",
          "is_active": "<boolean>",
          "is_locked": "<boolean>",
          "centers": [
            {
              "id": "<uuid>",
              "code": "<string>",
              "name": "<string>"
            }
          ],
          "centers_count": "<integer>",
          "redeemable_centers": [
            {
              "id": "<uuid>",
              "code": "<string>",
              "name": "<string>"
            }
          ],
          "redeemable_centers_count": "<integer>",
          "products": [
            {
              "id": "<uuid>",
              "name": "<string>",
              "code": "<string>"
            }
          ],
          "products_count": "<integer>",
          "created_at": "<datetime>",
          "updated_at": "<datetime>",
          "created_by": {
            "id": "<uuid>",
            "email": "<string|null>",
            "first_name": "<string>",
            "last_name": "<string>",
            "image": "<url|null>",
            "last_login": "<datetime|null>"
          }
        }
      ],
      "services_count": "<integer>",
      "is_active": "<boolean>",
      "created_at": "<datetime>",
      "updated_at": "<datetime>",
      "created_by": {
        "id": "<uuid>",
        "email": "<string|null>",
        "first_name": "<string>",
        "last_name": "<string>",
        "image": "<url|null>",
        "last_login": "<datetime|null>"
      }
    }
  ]
}
```

### POST Composite Template

#### URL

```text
<baseURL>/programs/composites/templates/
```

#### Request Payload

```json
{
  "code": "<string>",
  "name": "<string>",
  "description": "<string|null>",
  "add_services": [
    {
      "id": "<service_uuid>",
      "quantity": "<integer>"
    }
  ],
  "is_active": "<boolean>"
}
```

#### Response Structure

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<uuid>",
    "code": "<string>",
    "name": "<string>",
    "description": "<string|null>",
    "services": [
      {
        "id": "<service_uuid>",
        "name": "<string>",
        "quantity": "<integer>",
        "is_global": "<boolean>",
        "service_category": "<string>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>",
        "is_active": "<boolean>",
        "is_locked": "<boolean>",
        "centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "centers_count": "<integer>",
        "redeemable_centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "redeemable_centers_count": "<integer>",
        "products": [
          {
            "id": "<uuid>",
            "name": "<string>",
            "code": "<string>"
          }
        ],
        "products_count": "<integer>",
        "created_at": "<datetime>",
        "updated_at": "<datetime>",
        "created_by": {
          "id": "<uuid>",
          "email": "<string|null>",
          "first_name": "<string>",
          "last_name": "<string>",
          "image": "<url|null>",
          "last_login": "<datetime|null>"
        }
      }
    ],
    "services_count": "<integer>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": {
      "id": "<uuid>",
      "email": "<string|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<datetime|null>"
    }
  }
}
```

### GET Composite Template

#### URL

```text
<baseURL>/programs/composites/templates/<template_id>/
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "Details.",
  "data": {
    "id": "<uuid>",
    "code": "<string>",
    "name": "<string>",
    "description": "<string|null>",
    "services": [
      {
        "id": "<service_uuid>",
        "name": "<string>",
        "quantity": "<integer>",
        "is_global": "<boolean>",
        "service_category": "<string>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>",
        "is_active": "<boolean>",
        "is_locked": "<boolean>",
        "centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "centers_count": "<integer>",
        "redeemable_centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "redeemable_centers_count": "<integer>",
        "products": [
          {
            "id": "<uuid>",
            "name": "<string>",
            "code": "<string>"
          }
        ],
        "products_count": "<integer>",
        "created_at": "<datetime>",
        "updated_at": "<datetime>",
        "created_by": {
          "id": "<uuid>",
          "email": "<string|null>",
          "first_name": "<string>",
          "last_name": "<string>",
          "image": "<url|null>",
          "last_login": "<datetime|null>"
        }
      }
    ],
    "services_count": "<integer>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": {
      "id": "<uuid>",
      "email": "<string|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<datetime|null>"
    }
  }
}
```

### PUT/PATCH Composite Template

#### URL

```text
<baseURL>/programs/composites/templates/<template_id>/
```

#### Request Payload

```json
{
  "code": "<string>",
  "name": "<string>",
  "description": "<string|null>",
  "is_active": "<boolean>"
}
```

#### Response Structure

```json
{
  "detail": "<Modified successfully.|Updated successfully.>",
  "data": {
    "id": "<uuid>",
    "code": "<string>",
    "name": "<string>",
    "description": "<string|null>",
    "services": [
      {
        "id": "<service_uuid>",
        "name": "<string>",
        "quantity": "<integer>",
        "is_global": "<boolean>",
        "service_category": "<string>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>",
        "is_active": "<boolean>",
        "is_locked": "<boolean>",
        "centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "centers_count": "<integer>",
        "redeemable_centers": [
          {
            "id": "<uuid>",
            "code": "<string>",
            "name": "<string>"
          }
        ],
        "redeemable_centers_count": "<integer>",
        "products": [
          {
            "id": "<uuid>",
            "name": "<string>",
            "code": "<string>"
          }
        ],
        "products_count": "<integer>",
        "created_at": "<datetime>",
        "updated_at": "<datetime>",
        "created_by": {
          "id": "<uuid>",
          "email": "<string|null>",
          "first_name": "<string>",
          "last_name": "<string>",
          "image": "<url|null>",
          "last_login": "<datetime|null>"
        }
      }
    ],
    "services_count": "<integer>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": {
      "id": "<uuid>",
      "email": "<string|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<datetime|null>"
    }
  }
}
```

### GET Composite Template Services

#### URL

```text
<baseURL>/programs/composites/templates/<template_id>/services/?page=<page>&limit=<limit>
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<service_uuid>",
      "name": "<string>",
      "quantity": "<integer>",
      "is_global": "<boolean>",
      "service_category": "<string>",
      "service_category_code": "<therapy|assessment|consultation>",
      "image": "<url|null>",
      "is_active": "<boolean>",
      "is_locked": "<boolean>",
      "centers": [
        {
          "id": "<uuid>",
          "code": "<string>",
          "name": "<string>"
        }
      ],
      "centers_count": "<integer>",
      "redeemable_centers": [
        {
          "id": "<uuid>",
          "code": "<string>",
          "name": "<string>"
        }
      ],
      "redeemable_centers_count": "<integer>",
      "products": [
        {
          "id": "<uuid>",
          "name": "<string>",
          "code": "<string>"
        }
      ],
      "products_count": "<integer>",
      "created_at": "<datetime>",
      "updated_at": "<datetime>",
      "created_by": {
        "id": "<uuid>",
        "email": "<string|null>",
        "first_name": "<string>",
        "last_name": "<string>",
        "image": "<url|null>",
        "last_login": "<datetime|null>"
      }
    }
  ]
}
```

## Composite Programs

Composite-program responses expose `services_count` as the authoritative total
and the following read-only breakdown:

- `assessment_services_count`, `therapy_services_count`, and
  `consultation_services_count` count every assigned service in that category,
  including add-ons.
- `add_ons_count` counts services assigned with `add_on` assignment type. It is
  an overlapping subset and must not be added to the total or category counts.
- Counts include inactive and cancelled assigned services. The frontend must
  display the API values and must not calculate or submit them.

### GET Composite Programs

#### URL

```text
<baseURL>/centers/<center_id>/composite-programs/?search=<search>&active=<0|1>&expired=<0|1>&page=<page>&limit=<limit>
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<uuid>",
      "profile": {
        "id": "<uuid>",
        "contact_email": "<string|null>",
        "phone": "<string>",
        "first_name": "<string>",
        "last_name": "<string>",
        "gender": "<string|null>",
        "date_of_birth": "<date|null>",
        "image": "<url|null>",
        "home_center": {
          "id": "<uuid>",
          "code": "<string>",
          "name": "<string>"
        },
        "created_at": "<datetime>",
        "updated_at": "<datetime>"
      },
      "center": {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      },
      "composite_template": {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>",
        "is_active": "<boolean>"
      },
      "name": "<string>",
      "assessment_type": "<Baseline|null>",
      "assessment_type_code": "<baseline|null>",
      "template_description": "<string|null>",
      "program_type": "composite",
      "notes": "<string|null>",
      "expires_at": "<date>",
      "is_complimentary": "<boolean>",
      "price": "<decimal_string|null>",
      "redeemable_centers": [
        {
          "id": "<uuid>",
          "code": "<string>",
          "name": "<string>"
        }
      ],
      "redeemable_centers_count": "<integer>",
      "services": [
        {
          "id": "<uuid>",
          "service": {
            "id": "<uuid>",
            "name": "<string>",
            "service_category": "<string>",
            "service_category_code": "<therapy|assessment|consultation>",
            "image": "<url|null>"
          },
          "sessions_count": "<integer|null>",
          "sessions_used": "<integer|null>",
          "sessions_cancelled": "<integer|null>",
          "redeem_code": "<string|null>",
          "can_redeem": "<boolean>",
          "cancellation_reason": "<string|null>",
          "cancelled_by": "<user_object|null>",
          "cancelled_at": "<datetime|null>",
          "cancelled_date": "<date|null>",
          "created_date": "<date>",
          "created_by": "<user_object|null>",
          "is_active": "<boolean>",
          "created_at": "<datetime>",
          "updated_at": "<datetime>"
        }
      ],
      "services_count": "<integer>",
      "add_ons_count": "<integer>",
      "assessment_services_count": "<integer>",
      "therapy_services_count": "<integer>",
      "consultation_services_count": "<integer>",
      "cancellation_reason": "<string|null>",
      "cancelled_by": "<user_object|null>",
      "cancelled_at": "<datetime|null>",
      "cancelled_date": "<date|null>",
      "created_date": "<date>",
      "is_active": "<boolean>",
      "created_at": "<datetime>",
      "updated_at": "<datetime>",
      "created_by": "<user_object|null>"
    }
  ]
}
```

### POST Composite Program

#### URL

```text
<baseURL>/centers/<center_id>/composite-programs/
```

#### Request Payload Structure

For a template containing at least one active assessment service:

```json
{
  "profile_id": "<customer_profile_uuid>",
  "composite_template_id": "<composite_template_uuid>",
  "name": "<composite_program_name|null>",
  "assessment_type": "baseline",
  "notes": "<string|null>",
  "expires_at": "<date>",
  "is_complimentary": "<boolean>",
  "price": "<decimal|null>",
  "redeemable_centers": [
    {
      "id": "<center_uuid>"
    }
  ],
  "created_date": "<date>"
}
```

For a template without an active assessment service, omit the assessment-only
fields:

```json
{
  "profile_id": "<customer_profile_uuid>",
  "composite_template_id": "<composite_template_uuid>",
  "notes": "<string|null>",
  "expires_at": "<date>",
  "is_complimentary": "<boolean>",
  "price": "<decimal|null>",
  "redeemable_centers": [
    {
      "id": "<center_uuid>"
    }
  ],
  "created_date": "<date>"
}
```

`name` is currently used only for programs whose template contains an active
assessment service. It is optional and accepts a string, an empty string, or
`null`; the backend stores an empty string as `null`. `assessment_type` accepts
`"baseline"` or `null`; it is required when the selected template contains at
least one active assessment service. For templates without an active assessment
service, the field may be omitted, set to `null`, or set to `"baseline"`.

#### Response Structure

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<uuid>",
    "profile": {
      "id": "<uuid>",
      "contact_email": "<string|null>",
      "phone": "<string>",
      "first_name": "<string>",
      "last_name": "<string>",
      "gender": "<string|null>",
      "date_of_birth": "<date|null>",
      "image": "<url|null>",
      "home_center": {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      },
      "created_at": "<datetime>",
      "updated_at": "<datetime>"
    },
    "center": {
      "id": "<uuid>",
      "code": "<string>",
      "name": "<string>"
    },
    "composite_template": {
      "id": "<uuid>",
      "code": "<string>",
      "name": "<string>",
      "is_active": "<boolean>"
    },
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "template_description": "<string|null>",
    "program_type": "composite",
    "notes": "<string|null>",
    "expires_at": "<date>",
    "is_complimentary": "<boolean>",
    "price": "<decimal_string|null>",
    "redeemable_centers": [
      {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "redeemable_centers_count": "<integer>",
    "services": [
      {
        "id": "<uuid>",
        "service": {
          "id": "<uuid>",
          "name": "<string>",
          "service_category": "<string>",
          "service_category_code": "<therapy|assessment|consultation>",
          "image": "<url|null>"
        },
        "sessions_count": "<integer|null>",
        "sessions_used": "<integer|null>",
        "sessions_cancelled": "<integer|null>",
        "redeem_code": "<string|null>",
        "can_redeem": "<boolean>",
        "cancellation_reason": "<string|null>",
        "cancelled_by": "<user_object|null>",
        "cancelled_at": "<datetime|null>",
        "cancelled_date": "<date|null>",
        "created_date": "<date>",
        "created_by": "<user_object|null>",
        "is_active": "<boolean>",
        "created_at": "<datetime>",
        "updated_at": "<datetime>"
      }
    ],
    "services_count": "<integer>",
    "add_ons_count": "<integer>",
    "assessment_services_count": "<integer>",
    "therapy_services_count": "<integer>",
    "consultation_services_count": "<integer>",
    "cancellation_reason": "<string|null>",
    "cancelled_by": "<user_object|null>",
    "cancelled_at": "<datetime|null>",
    "cancelled_date": "<date|null>",
    "created_date": "<date>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": "<user_object|null>"
  }
}
```

### GET Composite Program

#### URL

```text
<baseURL>/programs/composites/programs/<program_id>/
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "Details.",
  "data": {
    "id": "<uuid>",
    "profile": {
      "id": "<uuid>",
      "contact_email": "<string|null>",
      "phone": "<string>",
      "first_name": "<string>",
      "last_name": "<string>",
      "gender": "<string|null>",
      "date_of_birth": "<date|null>",
      "image": "<url|null>",
      "home_center": {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      },
      "created_at": "<datetime>",
      "updated_at": "<datetime>"
    },
    "center": {
      "id": "<uuid>",
      "code": "<string>",
      "name": "<string>"
    },
    "composite_template": {
      "id": "<uuid>",
      "code": "<string>",
      "name": "<string>",
      "is_active": "<boolean>"
    },
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "template_description": "<string|null>",
    "program_type": "composite",
    "notes": "<string|null>",
    "expires_at": "<date|null>",
    "is_complimentary": "<boolean>",
    "price": "<decimal_string|null>",
    "redeemable_centers": [
      {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "redeemable_centers_count": "<integer>",
    "services": [
      {
        "id": "<uuid>",
        "service": {
          "id": "<uuid>",
          "name": "<string>",
          "service_category": "<string>",
          "service_category_code": "<therapy|assessment|consultation>",
          "image": "<url|null>"
        },
        "sessions_count": "<integer|null>",
        "sessions_used": "<integer|null>",
        "sessions_cancelled": "<integer|null>",
        "redeem_code": "<string|null>",
        "can_redeem": "<boolean>",
        "cancellation_reason": "<string|null>",
        "cancelled_by": "<user_object|null>",
        "cancelled_at": "<datetime|null>",
        "cancelled_date": "<date|null>",
        "created_date": "<date>",
        "created_by": "<user_object|null>",
        "is_active": "<boolean>",
        "created_at": "<datetime>",
        "updated_at": "<datetime>"
      }
    ],
    "services_count": "<integer>",
    "add_ons_count": "<integer>",
    "assessment_services_count": "<integer>",
    "therapy_services_count": "<integer>",
    "consultation_services_count": "<integer>",
    "cancellation_reason": "<string|null>",
    "cancelled_by": "<user_object|null>",
    "cancelled_at": "<datetime|null>",
    "cancelled_date": "<date|null>",
    "created_date": "<date>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": "<user_object|null>"
  }
}
```

### PUT/PATCH Composite Program

#### URL

```text
<baseURL>/programs/composites/programs/<program_id>/
```

#### Request Payload

```json
{
  "notes": "<string|null>",
  "expires_at": "<date|null>"
}
```

#### Response Structure

```json
{
  "detail": "<Modified successfully.|Updated successfully.>",
  "data": {
    "id": "<uuid>",
    "profile": "<customer_profile_object>",
    "center": "<center_object>",
    "composite_template": "<composite_template_reference_object>",
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "template_description": "<string|null>",
    "program_type": "composite",
    "notes": "<string|null>",
    "expires_at": "<date|null>",
    "is_complimentary": "<boolean>",
    "price": "<decimal_string|null>",
    "redeemable_centers": [
      {
        "id": "<uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "redeemable_centers_count": "<integer>",
    "services": [
      "<composite_program_service_object>"
    ],
    "services_count": "<integer>",
    "add_ons_count": "<integer>",
    "assessment_services_count": "<integer>",
    "therapy_services_count": "<integer>",
    "consultation_services_count": "<integer>",
    "cancellation_reason": "<string|null>",
    "cancelled_by": "<user_object|null>",
    "cancelled_at": "<datetime|null>",
    "cancelled_date": "<date|null>",
    "created_date": "<date>",
    "is_active": "<boolean>",
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": "<user_object|null>"
  }
}
```

`name`, `assessment_type`, and `assessment_type_code` are immutable and must
not be submitted through PUT or PATCH.

### POST Composite Program Add-Ons

The repeatable add-on workflow and current API contract are documented in
[Composite Program Add-Ons — Frontend ePRD](composite-program-add-ons-frontend-eprd.md).

### GET Composite Program Services

#### URL

```text
<baseURL>/programs/composites/programs/<program_id>/services/?page=<page>&limit=<limit>
```

#### Request Payload

```json
null
```

#### Response Structure

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<uuid>",
      "service": {
        "id": "<uuid>",
        "name": "<string>",
        "service_category": "<string>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>"
      },
      "sessions_count": "<integer|null>",
      "sessions_used": "<integer|null>",
      "sessions_cancelled": "<integer|null>",
      "redeem_code": "<string|null>",
      "can_redeem": "<boolean>",
      "cancellation_reason": "<string|null>",
      "cancelled_by": "<user_object|null>",
      "cancelled_at": "<datetime|null>",
      "cancelled_date": "<date|null>",
      "created_date": "<date>",
      "created_by": "<user_object|null>",
      "is_active": "<boolean>",
      "created_at": "<datetime>",
      "updated_at": "<datetime>"
    }
  ]
}
```

### POST Cancel Composite Program

#### URL

```text
<baseURL>/programs/composites/programs/<program_id>/cancel/
```

#### Request Payload

```json
{
  "cancellation_reason": "<string|null>",
  "cancelled_date": "<date>"
}
```

#### Response Structure

```json
{
  "detail": "Create success.",
  "data": {
    "cancellation_reason": "<string|null>",
    "cancelled_date": "<date>",
    "cancelled_by": {
      "id": "<uuid>",
      "email": "<string|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<datetime|null>"
    },
    "cancelled_at": "<datetime|null>"
  }
}
```

## Error Response

### URL

```text
<baseURL>/<requested_path>/
```

### Request Payload

```json
"<endpoint_request_payload|null>"
```

### Response Structure

```json
{
  "detail": "<string|object>"
}
```
