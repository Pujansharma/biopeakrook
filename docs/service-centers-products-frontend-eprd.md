# Service Centers and Products — Frontend ePRD

## 1. Purpose

Build the service-detail center and product list experiences using the generic
service relation endpoints:

- `GET /services/:service_id/centers/`
- `GET /services/:service_id/products/`

Both endpoints accept a service from any category and return paginated,
read-only data. They are suitable for complete-list screens, selectors, and
service-detail tabs. They do not add, remove, or update service assignments.

The existing assessment-specific center and product endpoints remain available
for existing consumers and are outside this integration.

## 2. Access and Shared Contract

```http
GET /services/<service_uuid>/centers/
Authorization: Bearer <access_token>
```

```http
GET /services/<service_uuid>/products/
Authorization: Bearer <access_token>
```

Authenticated administrators and associates can access both endpoints.
Customers cannot access them. Neither endpoint requires `X-Center-ID`.

`service_id` must be the UUID of an existing service. The same endpoints are
used for assessment, therapy, consultation, and any other service category.

### 2.1 Shared pagination parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `page` | No | Positive integer | Requested page; defaults to the first page |
| `limit` | No | Positive integer up to `50` | Page size; defaults to `10` |

### 2.2 Shared paginated envelope

Successful requests return `200 OK`:

```json
{
  "detail": "All data.",
  "count": 25,
  "next": "<next_page_url|null>",
  "previous": "<previous_page_url|null>",
  "data": []
}
```

`data` contains the current page only. Use `count` for the complete filtered
result count, and use `next` and `previous` for pagination state.

## 3. Service Centers

### 3.1 Endpoint

```http
GET /services/<service_uuid>/centers/
Authorization: Bearer <access_token>
```

### 3.2 Center-selection behavior

The returned center population depends on the resolved service:

| Service state | Centers considered before query filtering |
|---|---|
| `is_global = true` | No centers; global services do not retain center-assignment rows |
| `is_global = false` | Only centers assigned to the service |

The response does not include `is_global`. Obtain that value from the service
list or detail response when the UI needs to distinguish a global service's
empty center-assignment list from a non-global service with no assignments.

The endpoint does not implicitly restrict the result to active centers. Use
`active=1` when a UI should show active centers only.

### 3.3 Query parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `search` | No | String | Case-insensitive prefix match on center name or substring match on center code |
| `active` | No | `0`, `1` | `0` returns inactive centers; `1` returns active centers; other values are ignored |
| `page` | No | Positive integer | Requested page |
| `limit` | No | Positive integer up to `50` | Requested page size |

Trim search input before sending it. An empty value behaves like an omitted
parameter.

Example:

```http
GET /services/<service_uuid>/centers/?search=BLR&active=1&page=1&limit=20
Authorization: Bearer <access_token>
```

Centers are ordered by service-center assignment creation time, newest first.

### 3.4 Success response

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<center_uuid>",
      "code": "BLR001",
      "name": "Indiranagar"
    }
  ]
}
```

The center representation intentionally contains only `id`, `code`, and
`name`. The `active` filter still constrains the queryset, but `is_active` is
not returned on each item.

### 3.5 Frontend type

```ts
interface ServiceCenter {
  id: string;
  code: string;
  name: string;
}
```

## 4. Service Products

### 4.1 Endpoint

```http
GET /services/<service_uuid>/products/
Authorization: Bearer <access_token>
```

Products are always restricted to products assigned to the resolved service.
The service's `is_global` value has no effect on product selection.

### 4.2 Query parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `search` | No | String | Case-insensitive product-name search |
| `active` | No | `0`, `1` | `0` returns inactive products; `1` returns active products; other values are ignored |
| `provider` | No | Provider UUID; repeatable | Returns products belonging to any supplied provider |
| `page` | No | Positive integer | Requested page |
| `limit` | No | Positive integer up to `50` | Requested page size |

Send multiple provider filters by repeating the query parameter:

```http
GET /services/<service_uuid>/products/?provider=<provider_uuid_1>&provider=<provider_uuid_2>&active=1&page=1&limit=20
Authorization: Bearer <access_token>
```

Multiple provider values use inclusive `OR` behavior. A product matches when
its provider is any UUID in the request.

Search is case-insensitive and supports product-name substrings. Trim search
input before sending it; an empty value behaves like an omitted parameter.

Products are ordered by service-product assignment creation time, newest first.

### 4.3 Success response

```json
{
  "detail": "All data.",
  "count": 2,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<product_uuid_1>",
      "name": "Metabolic Health Panel",
      "code": "PC-0001"
    },
    {
      "id": "<product_uuid_2>",
      "name": "Advanced Health Panel",
      "code": "PC-0002"
    }
  ]
}
```

The product representation intentionally contains only `id`, `name`, and
`code`. It does not expose the product's provider or active state even when the
request filters by those fields. Use the request's selected filters as UI state;
do not expect those values on each returned item.

### 4.4 Frontend type

```ts
interface ServiceProduct {
  id: string;
  name: string;
  code: string;
}
```

## 5. Empty, Loading, and Error States

### 5.1 Empty result

A valid request with no matching records returns `200 OK`:

```json
{
  "detail": "All data.",
  "count": 0,
  "next": null,
  "previous": null,
  "data": []
}
```

Treat this as an empty list, not an error. Distinguish between an unfiltered
empty relation and filters that produce no matches when choosing UI copy.

### 5.2 Missing service

A well-formed UUID that does not identify a service returns `404 Not Found`:

```json
{
  "detail": "Service not found"
}
```

Do not replace this state with an empty center or product list. Navigate back
to the service catalogue or show that the selected service is unavailable.

An invalid UUID does not match the route and also returns a general `404`.

### 5.3 Authentication and authorization

- Missing or expired authentication returns the standard authentication error.
- A signed-in user who is neither an administrator nor an associate receives
  the standard permission error.
- Display the backend `detail` message and do not retry permission failures.

## 6. Frontend Integration Requirements

- Store the service UUID from the selected service and interpolate it into both
  endpoint paths; do not send it as a query parameter.
- Reset `page` to `1` whenever search, active state, or provider filters change.
- Debounce text search and cancel or ignore stale requests so an older response
  cannot replace a newer result.
- Preserve repeated `provider` keys when building the product query string.
- Use `active=1` explicitly when inactive catalogue records should be hidden;
  omission returns both active and inactive records.
- Keep center and product loading, error, pagination, and filter state separate.
- Do not use `X-Center-ID`; these are service-scoped global catalogue routes.
- Do not use these endpoints to infer or mutate assignments.

## 7. Acceptance Criteria

- An administrator or associate can paginate through centers and products for
  any valid service category.
- A global service returns an empty center-assignment list.
- A non-global service returns only its assigned centers after applying center
  filters.
- The product endpoint returns only products assigned to the service, regardless
  of `is_global`.
- Center search, active filtering, and assignment ordering are represented
  correctly in the UI.
- Product search, active filtering, repeatable provider filtering, and assignment
  ordering are represented correctly in the UI.
- Empty pages, missing services, authentication failures, and permission failures
  have distinct UI states.
- Existing assessment-specific endpoint consumers continue unchanged.
