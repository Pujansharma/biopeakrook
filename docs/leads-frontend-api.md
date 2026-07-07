# Leads Frontend API

## GET /leads/

Request:

```http
GET /leads/?search=bhaskar&active=1&is_client=0&center_id=9d9f1e6c-7b70-4c0f-b75d-0d9b44b0c111
```

Response:

```json
{
  "success": true,
  "detail": "All data.",
  "data": [
    {
      "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
      "unique_id": "L-0001",
      "first_name": "Bhaskar",
      "last_name": "Reddy",
      "gender": "Male",
      "phone": "+91-9123456780",
      "email": "reddybhaskar@biopeak.com",
      "description": "Interested in wellness program",
      "is_active": true,
      "is_client": false,
      "is_request_sent": false,
      "is_onboarding_sent": false,
      "converted_on": null,
      "home_center": {
        "id": "9d9f1e6c-7b70-4c0f-b75d-0d9b44b0c111",
        "code": "CT-0001",
        "name": "Greenwood",
        "image": null,
        "address": "Greenwood Main Road",
        "address_line_1": "Greenwood Main Road",
        "address_line_2": null,
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "India",
        "pincode": "560001",
        "staff_count": 12,
        "inactive_staff_count": 1,
        "customer_count": 240,
        "inactive_customer_count": 8,
        "is_active": true,
        "created_at": "2026-07-07T10:00:00+05:30",
        "updated_at": "2026-07-07T10:00:00+05:30"
      },
      "customer_profile": null,
      "created_by": {
        "id": "2e6f5d29-7cc0-4e9e-9e3d-fc1f7a111111",
        "email": "admin@biopeak.com",
        "first_name": "Admin",
        "last_name": "User",
        "image": null,
        "last_login": "2026-07-07T09:30:00+05:30"
      },
      "updated_by": null,
      "created_at": "2026-07-07T10:30:00+05:30",
      "updated_at": "2026-07-07T10:30:00+05:30"
    }
  ]
}
```

## POST /leads/

Request:

```http
POST /leads/
```

```json
{
  "first_name": "Bhaskar",
  "last_name": "Reddy",
  "gender": "M",
  "phone": "+91-9123456780",
  "email": "reddybhaskar@biopeak.com",
  "description": "Interested in wellness program",
  "is_active": true,
  "is_client": false
}
```

Response:

```json
{
  "success": true,
  "detail": "Create success.",
  "data": {
    "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
    "unique_id": "L-0001",
    "first_name": "Bhaskar",
    "last_name": "Reddy",
    "gender": "Male",
    "phone": "+91-9123456780",
    "email": "reddybhaskar@biopeak.com",
    "description": "Interested in wellness program",
    "is_active": true,
    "is_client": false,
    "is_request_sent": false,
    "is_onboarding_sent": false,
    "converted_on": null,
    "home_center": null,
    "customer_profile": null,
    "created_by": {
      "id": "2e6f5d29-7cc0-4e9e-9e3d-fc1f7a111111",
      "email": "admin@biopeak.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": null,
      "last_login": "2026-07-07T09:30:00+05:30"
    },
    "updated_by": null,
    "created_at": "2026-07-07T10:30:00+05:30",
    "updated_at": "2026-07-07T10:30:00+05:30"
  }
}
```

## GET /leads/{lead_id}/

Request:

```http
GET /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/
```

Response:

```json
{
  "success": true,
  "detail": "Details.",
  "data": {
    "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
    "unique_id": "L-0001",
    "first_name": "Bhaskar",
    "last_name": "Reddy",
    "gender": "Male",
    "phone": "+91-9123456780",
    "email": "reddybhaskar@biopeak.com",
    "description": "Interested in wellness program",
    "is_active": true,
    "is_client": false,
    "is_request_sent": false,
    "is_onboarding_sent": false,
    "converted_on": null,
    "home_center": null,
    "customer_profile": null,
    "created_by": {
      "id": "2e6f5d29-7cc0-4e9e-9e3d-fc1f7a111111",
      "email": "admin@biopeak.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": null,
      "last_login": "2026-07-07T09:30:00+05:30"
    },
    "updated_by": null,
    "created_at": "2026-07-07T10:30:00+05:30",
    "updated_at": "2026-07-07T10:30:00+05:30"
  }
}
```

## PATCH /leads/{lead_id}/

Request:

```http
PATCH /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/
```

```json
{
  "is_client": true,
  "is_active": true
}
```

Response:

```json
{
  "success": true,
  "detail": "Updated successfully.",
  "data": {
    "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
    "unique_id": "L-0001",
    "first_name": "Bhaskar",
    "last_name": "Reddy",
    "gender": "Male",
    "phone": "+91-9123456780",
    "email": "reddybhaskar@biopeak.com",
    "description": "Interested in wellness program",
    "is_active": true,
    "is_client": true,
    "is_request_sent": false,
    "is_onboarding_sent": false,
    "converted_on": null,
    "home_center": null,
    "customer_profile": null,
    "created_by": {
      "id": "2e6f5d29-7cc0-4e9e-9e3d-fc1f7a111111",
      "email": "admin@biopeak.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": null,
      "last_login": "2026-07-07T09:30:00+05:30"
    },
    "updated_by": {
      "id": "2e6f5d29-7cc0-4e9e-9e3d-fc1f7a111111",
      "email": "admin@biopeak.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": null,
      "last_login": "2026-07-07T09:30:00+05:30"
    },
    "created_at": "2026-07-07T10:30:00+05:30",
    "updated_at": "2026-07-07T10:45:00+05:30"
  }
}
```

## POST /leads/{lead_id}/share-onboarding/

Request:

```http
POST /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/share-onboarding/
```

```json
{}
```

Response:

```json
{
  "success": true,
  "detail": "Create success.",
  "data": {
    "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
    "is_request_sent": true,
    "is_onboarding_sent": true
  }
}
```

## POST /leads/{lead_id}/convert-client/

Request:

```http
POST /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/convert-client/
```

```json
{}
```

Response:

```json
{
  "success": true,
  "detail": "Create success.",
  "data": {
    "id": "1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10",
    "is_client": true,
    "converted_on": "2026-07-07T11:00:00+05:30",
    "customer_profile": "7a3d1172-21a7-4697-9d31-62c33fdc2222"
  }
}
```

## GET /leads/{lead_id}/available-packages/

Request:

```http
GET /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/available-packages/
```

Response:

```json
{
  "success": true,
  "detail": "All data.",
  "data": []
}
```

## POST /leads/{lead_id}/assign-package/

Request:

```http
POST /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/assign-package/
```

```json
{
  "add": [
    {
      "id": "8c9f4f66-2bc8-4a7c-8577-88c11f333333"
    }
  ],
  "remove": [
    {
      "id": "0936634b-79c2-46c8-8b68-dc702f444444"
    }
  ]
}
```

Response:

```json
{
  "success": false,
  "detail": "Composite package assignment is unavailable until composite models are implemented."
}
```

## GET /leads/{lead_id}/packages/

Request:

```http
GET /leads/1f8f96f2-6d7e-4d52-9d1f-6fd7e09b2c10/packages/
```

Response:

```json
{
  "success": true,
  "detail": "All data.",
  "data": []
}
```
