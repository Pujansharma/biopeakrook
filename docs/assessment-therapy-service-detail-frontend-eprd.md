# Assessment and Therapy Service Detail — Frontend ePRD

## 1. Purpose

Build the frontend detail, edit, and delete experience for assessment and
therapy service definitions.

This ePRD is for frontend implementation only and covers these backend routes:

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | Retrieve an assessment service | `/services/assessment-services/:service_id/` |
| `PATCH` | Partially update an assessment service | `/services/assessment-services/:service_id/` |
| `PUT` | Update an assessment service | `/services/assessment-services/:service_id/` |
| `DELETE` | Delete an assessment service | `/services/assessment-services/:service_id/` |
| `GET` | Retrieve a therapy service | `/services/therapy-services/:service_id/` |
| `PATCH` | Partially update a therapy service | `/services/therapy-services/:service_id/` |
| `PUT` | Update a therapy service | `/services/therapy-services/:service_id/` |
| `DELETE` | Delete a therapy service | `/services/therapy-services/:service_id/` |

`service_id` is the service UUID. An ID belonging to a different service
category is treated as not found on the selected endpoint.

Service list, creation, complete center/product selection, therapy redemption,
and program-service cancellation are outside this document's scope.

## 2. Access and Request Context

All requests require a valid JWT:

```http
Authorization: Bearer <access_token>
```

Access is determined by account type:

| Account type | `GET` | `PATCH` / `PUT` | `DELETE` |
|---|---:|---:|---:|
| Administrator | Allowed | Allowed | Allowed |
| Associate | Allowed | Not allowed | Not allowed |
| Customer | Not allowed | Not allowed | Not allowed |

These routes do not require `X-Center-ID`. Associate access is read-only but is
not restricted to the associate's assigned centers by these detail endpoints.

Use `Content-Type: application/json` for updates that do not upload an image.
Use `multipart/form-data` when submitting a new image file.

## 3. Product Behavior

Use one shared service-detail page with a category-specific configuration:

| Capability | Assessment | Therapy |
|---|---:|---:|
| View core service information | Yes | Yes |
| Edit name, image, global status, active status, and centers | Admin only | Admin only |
| View and edit products | Admin can edit; associates can view | No |
| Delete | Admin only | Admin only |

The page must provide:

- service identity and category;
- image, active status, and global/local availability status;
- assigned-center count and a center preview;
- assessment-only product count and product preview;
- creator and audit metadata;
- admin-only edit and delete actions;
- read-only presentation for associates.

The frontend must use the endpoint selected by the service category. It must
not try the assessment endpoint and fall back to the therapy endpoint after a
`404`.

## 4. GET Service Detail

### 4.1 Assessment request

```http
GET /services/assessment-services/:service_id/
Authorization: Bearer <access_token>
```

Request body:

```json
null
```

### 4.2 Therapy request

```http
GET /services/therapy-services/:service_id/
Authorization: Bearer <access_token>
```

Request body:

```json
null
```

### 4.3 Success status

```text
200 OK
```

### 4.4 Assessment response

```json
{
  "detail": "Details.",
  "data": {
    "id": "<service_uuid>",
    "name": "<string>",
    "is_global": "<boolean>",
    "service_category": "Assessment",
    "service_category_code": "assessment",
    "image": "<url|null>",
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>",
    "is_active": "<boolean>",
    "is_locked": "<boolean>",
    "created_by": {
      "id": "<user_uuid>",
      "email": "<email|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    },
    "centers_count": "<integer>",
    "centers": [
      {
        "id": "<center_uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "products_count": "<integer>",
    "products": [
      {
        "id": "<product_uuid>",
        "name": "<string>",
        "code": "<string>"
      }
    ]
  }
}
```

`created_by` can be `null` because the backend relation is nullable.

### 4.5 Therapy response

```json
{
  "detail": "Details.",
  "data": {
    "id": "<service_uuid>",
    "name": "<string>",
    "is_global": "<boolean>",
    "service_category": "Therapy",
    "service_category_code": "therapy",
    "image": "<url|null>",
    "centers_count": "<integer>",
    "centers": [
      {
        "id": "<center_uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>",
    "is_active": "<boolean>",
    "is_locked": "<boolean>",
    "created_by": {
      "id": "<user_uuid>",
      "email": "<email|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    }
  }
}
```

`created_by` can also be `null` on a therapy service.

### 4.6 Preview semantics

`centers` is a preview containing at most three assigned centers. It is an
empty array when no center is assigned. `centers_count` is the authoritative
total and can be greater than `centers.length`.

For assessment services, `products` is also a preview containing at most three
assigned products. It is an empty array when none is assigned.
`products_count` is the authoritative total and can be greater than
`products.length`.

The frontend must not calculate either count from a preview array.

For assessment services, setting `is_global` to `true` clears center
assignments. The UI should present that service as available globally and
should not interpret an empty center preview as unavailable.

The current therapy update behavior does not clear center assignments when
`is_global` becomes `true`. A therapy response can therefore contain both
`is_global: true` and assigned centers. Render the values supplied by the API;
do not normalize the therapy center list in client state.

### 4.7 Lock-state limitation

The current detail query does not calculate a relationship-based lock state.
Consequently, `is_locked` currently defaults to `false` on these responses.
The frontend must not treat `is_locked: false` as a guarantee that deletion
will succeed. The `DELETE` response remains authoritative.

## 5. PATCH and PUT Service Detail

### 5.1 Frontend method

Use `PATCH` for ordinary edits. Use `PUT` only when intentionally sending the
complete editable core resource; `PUT` requires `name`, while `PATCH` does not.

### 5.2 Shared editable fields

| Field | Type | Rules |
|---|---|---|
| `name` | `string` | Required for `PUT`; optional for `PATCH`; cannot be blank; maximum 200 characters |
| `is_global` | `boolean` | Optional; category-specific center behavior is described in section 5.6 |
| `image` | `file \| null` | Optional; send a file with multipart data; send `null` to clear the image |
| `is_active` | `boolean` | Optional |
| `add_centers` | `{ id: UUID }[] \| null` | Optional; IDs of centers to assign |
| `remove_centers` | `{ id: UUID }[] \| null` | Optional; IDs of centers to unassign |

Assessment services additionally accept:

| Field | Type | Rules |
|---|---|---|
| `add_products` | `{ id: UUID }[] \| null` | Optional; IDs of products to assign |
| `remove_products` | `{ id: UUID }[] \| null` | Optional; IDs of products to unassign |

Therapy services do not accept product-assignment fields.

### 5.3 Read-only fields

Do not submit these response fields in an edit payload:

- `id`;
- `service_category`;
- `service_category_code`;
- `centers`;
- `centers_count`;
- `products`;
- `products_count`;
- `is_locked`;
- `created_by`;
- `created_at`;
- `updated_at`.

The frontend must build a dedicated update payload instead of submitting the
complete GET response.

### 5.4 JSON PATCH examples

Update core assessment fields:

```http
PATCH /services/assessment-services/:service_id/
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "name": "Advanced Metabolic Assessment",
  "is_active": true
}
```

Update assessment assignments:

```json
{
  "add_centers": [
    { "id": "<center_uuid>" }
  ],
  "remove_centers": [
    { "id": "<center_uuid>" }
  ],
  "add_products": [
    { "id": "<product_uuid>" }
  ],
  "remove_products": [
    { "id": "<product_uuid>" }
  ]
}
```

Update therapy assignments:

```http
PATCH /services/therapy-services/:service_id/
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "is_global": false,
  "add_centers": [
    { "id": "<center_uuid>" }
  ],
  "remove_centers": []
}
```

### 5.5 Image update

Send an image update as multipart form data. The exact boundary is generated by
the browser and must not be manually set.

```http
PATCH /services/assessment-services/:service_id/
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=<browser_generated_boundary>
```

Multipart fields:

```text
image=<binary_file>
```

If a multipart request also changes assignment arrays, serialize them in the
form-data convention already used by the frontend API client. A simpler and
less error-prone flow is to send the image and relationship changes in
separate PATCH requests.

### 5.6 Global service behavior

For an assessment service, when an update resolves to `is_global: true`, the
backend:

- removes every assigned center;
- ignores `add_centers` and `remove_centers` in that request;
- updates `centers_count` to zero.

On the assessment form, disable the center picker while the global toggle is
on and omit center mutations from the payload.

For a therapy service, changing `is_global` does not automatically clear
centers, and center mutations in the same request are still processed. Do not
discard therapy centers locally when the global toggle is enabled.

When changing either category from `is_global: true` to `false`, the backend
does not require a center in the same request. The frontend should not invent a
validation rule without product confirmation; it may submit selected centers
when the product flow requires local availability.

### 5.7 Assignment conflict behavior

For both center and assessment-product mutations, the backend processes adds
before removals. If the same ID is present in both arrays, removal wins.

The frontend should prevent an ID from appearing in both arrays. Duplicate
assignments are otherwise ignored by the backend.

### 5.8 Assessment product invariant

An assessment service must retain at least one assigned product after an
update. If an update would leave the service with zero products, the entire
request is rolled back and the API returns:

```json
{
  "detail": "No products associated with the service"
}
```

The frontend should prevent removal of the final product and must still handle
the API error in case the local state is stale.

### 5.9 PATCH success response

```text
200 OK
```

```json
{
  "detail": "Updated successfully.",
  "data": "<complete_category_specific_service_detail_object>"
}
```

### 5.10 PUT success response

```text
200 OK
```

```json
{
  "detail": "Modified successfully.",
  "data": "<complete_category_specific_service_detail_object>"
}
```

Assessment update responses include refreshed center/product counts and
previews.

The current therapy update response can contain the center preview and
`centers_count` from before the center mutation. After a successful therapy
update that changes `is_global`, `add_centers`, or `remove_centers`, refetch the
therapy detail endpoint before rendering final assignment state.

## 6. DELETE Service Detail

### 6.1 Request

Assessment:

```http
DELETE /services/assessment-services/:service_id/
Authorization: Bearer <access_token>
```

Therapy:

```http
DELETE /services/therapy-services/:service_id/
Authorization: Bearer <access_token>
```

Request body:

```json
null
```

Only administrators can delete. Show a confirmation dialog containing the
service name and make the destructive action explicit.

### 6.2 Success response

```text
200 OK
```

```json
{
  "detail": "Deleted successfully."
}
```

After success, remove the detail query from the client cache and navigate back
to the appropriate category list.

### 6.3 Protected service response

A service referenced by protected records cannot be deleted. The expected
response is:

```text
400 Bad Request
```

```json
{
  "detail": "This service cannot be deleted"
}
```

Assessment product assignments use a protected relationship. Therefore, an
assessment service that still has its required product assignment will reject
deletion. Do not optimistically remove a service from cached lists before the
API confirms success.

## 7. Error Handling

Errors do not contain `data`. The `detail` value can be a string or an object.

Field validation example:

```json
{
  "detail": {
    "name": [
      "This field may not be blank."
    ]
  }
}
```

Invalid assignment example:

```json
{
  "detail": {
    "add_centers": "Invalid center IDs provided: <center_uuid>"
  }
}
```

General error:

```json
{
  "detail": "<error_message>"
}
```

Expected status handling:

| Status | Frontend behavior |
|---|---|
| `400` | Map object-shaped `detail` to fields; otherwise show the returned message |
| `401` | Start the application's authentication recovery flow |
| `403` | Show an access-denied state or remove unauthorized mutation controls |
| `404` | Show service-not-found for the selected category |
| `500` | Show the standard retryable server-error state |

The frontend must support both string-shaped and object-shaped `detail`.

## 8. Recommended Frontend Data Contracts

```ts
type ServiceCategoryCode = "assessment" | "therapy";

interface MinimumCenter {
  id: string;
  code: string;
  name: string;
}

interface MinimumProduct {
  id: string;
  name: string;
  code: string;
}

interface BaseUser {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  image: string | null;
  last_login: string | null;
}

interface ServiceDetailBase {
  id: string;
  name: string;
  is_global: boolean;
  image: string | null;
  centers_count: number;
  centers: MinimumCenter[];
  created_at: string;
  updated_at: string;
  is_active: boolean;
  is_locked: boolean;
  created_by: BaseUser | null;
}

interface AssessmentServiceDetail extends ServiceDetailBase {
  service_category: "Assessment";
  service_category_code: "assessment";
  products_count: number;
  products: MinimumProduct[];
}

interface TherapyServiceDetail extends ServiceDetailBase {
  service_category: "Therapy";
  service_category_code: "therapy";
}

interface RelationshipIdentifier {
  id: string;
}

interface ServiceUpdatePayload {
  name?: string;
  is_global?: boolean;
  image?: File | null;
  is_active?: boolean;
  add_centers?: RelationshipIdentifier[] | null;
  remove_centers?: RelationshipIdentifier[] | null;
}

interface AssessmentServiceUpdatePayload extends ServiceUpdatePayload {
  add_products?: RelationshipIdentifier[] | null;
  remove_products?: RelationshipIdentifier[] | null;
}

interface DetailResponse<T> {
  detail: string;
  data: T;
}

interface APIErrorResponse {
  detail: string | Record<string, string | string[]>;
}
```

Use `service_category_code`, not the display label, for frontend branching.

## 9. State and Cache Rules

- Include the service category and service UUID in the detail query key.
- Replace assessment detail state with the successful mutation response.
- Refetch therapy detail after any center/global mutation.
- Invalidate the applicable service-list query after every successful update or
  delete.
- Do not derive counts from preview arrays.
- Do not optimistically delete; protected relationships can reject the request.
- Changing from an admin to an associate session must remove edit and delete
  controls even if cached detail data remains available.

## 10. Acceptance Criteria

- The assessment route loads only assessment service IDs.
- The therapy route loads only therapy service IDs.
- A valid admin or associate sees the category-appropriate detail response.
- Associates see a read-only page with no edit or delete actions.
- Customers and unauthenticated users are routed through the application's
  access-error flow.
- Center and product counts are displayed from count fields, not preview-array
  lengths.
- The products section appears only for assessment services.
- Admin edits use `PATCH` by default and submit only editable fields.
- Image uploads use multipart form data.
- Enabling global availability for an assessment service disables center
  selection and omits center mutations.
- Therapy global-status changes preserve API-supplied center state rather than
  applying the assessment clearing behavior.
- The same center or product cannot be staged for both addition and removal.
- The assessment UI prevents removal of the final assigned product.
- Assessment mutation success replaces local detail state with response data.
- Therapy center/global mutation success triggers a detail refetch.
- Delete requires confirmation and waits for API success before navigation.
- Protected-delete errors keep the detail page intact and show the returned
  message.
- String-shaped and object-shaped error details are both handled.
