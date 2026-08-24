# Associate List and Create — Frontend ePRD

## 1. Purpose

Build the administrator-facing associate list and associate-creation flow using
the shared `/associates/` collection endpoint.

- `GET /associates/` returns a paginated list of associates.
- `POST /associates/` creates an associate and assigns one or more centers.

The current read representation includes a limited center preview without
center-assignment flags. `is_admin` and `is_care_staff` are accepted and saved
during creation, but they are not returned inside the `centers` preview yet.

Associate detail, update, deletion, complete assigned-center lists, and later
center-linking changes are outside this ePRD.

## 2. Endpoint and Access

```http
GET /associates/
Authorization: Bearer <access_token>
```

```http
POST /associates/
Authorization: Bearer <access_token>
Content-Type: application/json
```

Only authenticated administrators can access either method. The endpoint is
global and does not require `X-Center-ID`.

Use `multipart/form-data` instead of JSON when the create request includes an
image file. Do not set the multipart boundary manually.

## 3. GET Associate List

### 3.1 Query parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `search` | No | String | Case-insensitive prefix match against email, national phone text, or full name |
| `active` | No | `0`, `1` | Filters inactive or active associates; other values are ignored |
| `admin` | No | `0`, `1` | Filters using center-assignment `is_admin`; see the semantics below |
| `page` | No | Positive integer | Requested page; defaults to the first page |
| `limit` | No | Positive integer up to `50` | Page size; defaults to `10` |

Trim `search` before submitting it. An empty search has the same behavior as
omitting the parameter. Search is prefix-based, so a middle-only substring is
not guaranteed to match.

Admin-filter behavior is assignment-based:

| UI value | Query value | Meaning |
|---|---|---|
| All | Omit `admin` | Do not filter by center admin responsibility |
| Admin at a center | `admin=1` | Associate has at least one center assignment with `is_admin=true` |
| Non-admin at a center | `admin=0` | Associate has at least one center assignment with `is_admin=false` |

`admin=0` does not mean the associate is never an administrator. An associate
who is an admin at one center and a non-admin at another can match both filter
values in separate requests.

Example:

```http
GET /associates/?search=meera&active=1&admin=1&page=1&limit=10
Authorization: Bearer <access_token>
```

Associates are ordered by creation time, newest first.

### 3.2 Success response

A successful request returns `200 OK`:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<associate_user_uuid>",
      "email": "meera@example.com",
      "contact_phone": "+919876543210",
      "first_name": "Meera",
      "last_name": "Shah",
      "gender": "Female",
      "date_of_birth": "1988-04-12",
      "image": "<image_url|null>",
      "is_external": false,
      "is_active": true,
      "date_joined": "2026-08-24",
      "last_login": null,
      "updated_at": "<ISO-8601_datetime>",
      "title": "Dr.",
      "description": "Endocrinologist",
      "tagline": "Metabolic health specialist",
      "experience": 10.5,
      "qualifications": ["MBBS", "MD"],
      "professions": ["Endocrinologist"],
      "centers_count": 2,
      "centers": [
        {
          "id": "<center_uuid>",
          "code": "BLR001",
          "name": "Indiranagar"
        }
      ]
    }
  ]
}
```

### 3.3 Center preview contract

`centers_count` is the persisted count of all center assignments for the
associate. `centers` is only a preview of up to three assignments, ordered by
the newest assignment first.

Each preview entry currently contains only:

```ts
interface MinimumCenter {
  id: string;
  code: string;
  name: string;
}
```

The preview does not currently include:

- `is_admin`;
- `is_care_staff`;
- role, mode, primary status, or assignment active status;
- every assigned center when `centers_count` is greater than three.

Do not infer either responsibility flag from the center preview. A future API
enhancement can add those flags without changing the create payload described
below.

## 4. POST Create Associate

### 4.1 Request payload

```json
{
  "email": "meera@example.com",
  "password1": "StrongPassword123!",
  "password2": "StrongPassword123!",
  "first_name": "Meera",
  "last_name": "Shah",
  "contact_phone": "+919876543210",
  "gender": "1",
  "date_of_birth": "1988-04-12",
  "is_external": false,
  "is_active": true,
  "date_joined": "2026-08-24",
  "title": "doctor",
  "description": "Endocrinologist",
  "tagline": "Metabolic health specialist",
  "experience": 10.5,
  "qualifications": ["MBBS", "MD"],
  "professions": ["Endocrinologist"],
  "add_centers": [
    {
      "id": "<center_uuid_1>",
      "is_admin": true,
      "is_care_staff": true
    },
    {
      "id": "<center_uuid_2>",
      "is_admin": false,
      "is_care_staff": true
    }
  ]
}
```

### 4.2 Associate fields

| Field | Required | Type | Rules |
|---|---|---|---|
| `email` | Yes | Email string | Must be unique, compared case-insensitively |
| `password1` | Yes | String | Must match `password2` and pass the configured password validators |
| `password2` | Yes | String | Confirmation of `password1` |
| `add_centers` | Yes | Non-empty array | Center-assignment input described in section 4.3 |
| `contact_phone` | No | String or `null` | Phone number with country code; Indian-region parsing is the default |
| `first_name` | No | String or `null` | Maximum 100 characters |
| `last_name` | No | String or `null` | Maximum 100 characters |
| `gender` | No | `"0"`, `"1"`, `"2"`, or `null` | Submit the code, not the display label |
| `date_of_birth` | No | `YYYY-MM-DD` or `null` | Associate's date of birth |
| `image` | No | File or `null` | Send the request as multipart when uploading a file |
| `is_external` | No | Boolean | Defaults to `false` |
| `is_active` | No | Boolean | Defaults to `true` |
| `date_joined` | No | `YYYY-MM-DD` or `null` | Business joining date, separate from account creation time |
| `title` | No | `"doctor"`, `"prof"`, or `null` | Submit the code; responses use the display label |
| `description` | No | String or `null` | May be blank |
| `tagline` | No | String or `null` | Maximum 100 characters; may be blank |
| `experience` | No | Number or `null` | Positive values are accepted; zero is normalized to `null`, and negative values are rejected |
| `qualifications` | No | String array | Maximum two entries; each entry has a 50-character maximum |
| `professions` | No | String array | Maximum two entries; each entry has a 50-character maximum |

Current gender mappings:

| Code | Display value |
|---|---|
| `"0"` | Male |
| `"1"` | Female |
| `"2"` | Other |

Current title mappings:

| Code | Display value |
|---|---|
| `doctor` | Dr. |
| `prof` | Prof. |

The current password fields accept no more than 50 characters. The password
must also pass Django's configured similarity, minimum-length, common-password,
and numeric-password checks. Display backend password messages rather than
duplicating the full validator logic in the client.

### 4.3 `add_centers` contract

```ts
interface AssociateCenterAssignmentInput {
  id: string;
  is_admin?: boolean;
  is_care_staff?: boolean;
}
```

| Field | Required | Default | Rules |
|---|---|---|---|
| `id` | Yes | None | Must be the UUID of an existing center |
| `is_admin` | No | `false` | Grants center-specific administrative responsibility |
| `is_care_staff` | No | `false` | Grants center-specific care-staff responsibility |

For every added center, at least one responsibility flag must be `true`:

```text
is_admin || is_care_staff
```

Valid combinations:

| `is_admin` | `is_care_staff` | Result |
|---:|---:|---|
| `true` | `false` | Valid |
| `false` | `true` | Valid |
| `true` | `true` | Valid |
| `false` | `false` | Invalid |

If the same center UUID occurs multiple times, the backend keeps the final
occurrence and its flags. The frontend should prevent duplicate center rows so
the user's intended responsibility state is unambiguous.

Center validation checks existence, not active status. Do not assume that the
backend will reject an inactive center; the center picker should apply the
product's intended availability rules before submission.

### 4.4 Atomic creation behavior

The backend validates the complete payload before saving. It then creates the
user, associate, associate account, and all center assignments in one database
transaction.

If any creation step fails, none of those records are committed. A successful
request also refreshes the affected center staff counters and the associate's
persisted `centers_count`.

### 4.5 Success response

A successful request returns `201 Created`:

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<associate_user_uuid>",
    "email": "meera@example.com",
    "contact_phone": "+919876543210",
    "first_name": "Meera",
    "last_name": "Shah",
    "gender": "Female",
    "date_of_birth": "1988-04-12",
    "image": null,
    "is_external": false,
    "is_active": true,
    "date_joined": "2026-08-24",
    "last_login": null,
    "updated_at": "<ISO-8601_datetime>",
    "title": "Dr.",
    "description": "Endocrinologist",
    "tagline": "Metabolic health specialist",
    "experience": 10.5,
    "qualifications": ["MBBS", "MD"],
    "professions": ["Endocrinologist"],
    "centers_count": 0,
    "centers": [
      {
        "id": "<center_uuid_2>",
        "code": "BLR002",
        "name": "Grace Towers"
      },
      {
        "id": "<center_uuid_1>",
        "code": "BLR001",
        "name": "Indiranagar"
      }
    ]
  }
}
```

`add_centers`, `password1`, and `password2` are write-only and are never
returned. The response's `centers` preview omits `is_admin` and
`is_care_staff`, even though both flags were persisted on the assignments.

The backend refreshes `centers_count` directly in the database but does not
reload the just-created serializer instance. Therefore, the POST response can
return a stale value such as `0` for `centers_count`. Treat a follow-up
`GET /associates/` as the authoritative list refresh after creation rather
than relying on the create response for derived counter or preview state.

## 5. Frontend Types

```ts
type AssociateActiveFilter = "0" | "1";
type AssociateAdminFilter = "0" | "1";
type GenderCode = "0" | "1" | "2";
type GenderLabel = "Male" | "Female" | "Other";
type AssociateTitleCode = "doctor" | "prof";
type AssociateTitleLabel = "Dr." | "Prof.";

interface AssociateListFilters {
  search?: string;
  active?: AssociateActiveFilter;
  admin?: AssociateAdminFilter;
  page: number;
  limit: number;
}

interface MinimumCenter {
  id: string;
  code: string;
  name: string;
}

interface AssociateListItem {
  id: string;
  email: string | null;
  contact_phone: string | null;
  first_name: string | null;
  last_name: string | null;
  gender: GenderLabel | null;
  date_of_birth: string | null;
  image: string | null;
  is_external: boolean;
  is_active: boolean;
  date_joined: string | null;
  last_login: string | null;
  updated_at: string;
  title: AssociateTitleLabel | null;
  description: string | null;
  tagline: string | null;
  experience: number | null;
  qualifications: string[];
  professions: string[];
  centers_count: number;
  centers: MinimumCenter[];
}

interface AssociateCenterAssignmentInput {
  id: string;
  is_admin?: boolean;
  is_care_staff?: boolean;
}

interface CreateAssociatePayload {
  email: string;
  password1: string;
  password2: string;
  add_centers: AssociateCenterAssignmentInput[];
  contact_phone?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  gender?: GenderCode | null;
  date_of_birth?: string | null;
  image?: File | null;
  is_external?: boolean;
  is_active?: boolean;
  date_joined?: string | null;
  title?: AssociateTitleCode | null;
  description?: string | null;
  tagline?: string | null;
  experience?: number | null;
  qualifications?: string[];
  professions?: string[];
}

interface AssociateListResponse {
  detail: "All data.";
  count: number;
  next: string | null;
  previous: string | null;
  data: AssociateListItem[];
}

interface CreateAssociateResponse {
  detail: "Create success.";
  data: AssociateListItem;
}
```

The backend returns display labels for `gender` and `title`, but creation
accepts their codes. Keep separate input-code and response-label types.

## 6. Error Responses

Errors use the standard response envelope and do not include `data`:

```json
{
  "detail": "<error_message_or_field_map>"
}
```

Example field error:

```json
{
  "detail": {
    "add_centers": "At least one of 'is_admin' or 'is_care_staff' must be true for centers: ['<center_uuid>']"
  }
}
```

Example missing-center error:

```json
{
  "detail": {
    "add_centers": "Centers not found: ['<center_uuid>']"
  }
}
```

| Status | Condition |
|---|---|
| `400` | A required create field is missing or `add_centers` is empty |
| `400` | Email, phone, date, choice, image, or list data is malformed |
| `400` | Passwords do not match or the password fails validation |
| `400` | An associate user with the email already exists |
| `400` | A center UUID is malformed or does not exist |
| `400` | An added center has both responsibility flags false or omitted |
| `401` | Authentication is missing or invalid |
| `403` | The authenticated user is not an administrator |

Field errors can be strings or arrays depending on which validation layer
rejects the request. Preserve backend messages and associate them with the
matching form field when possible.

## 7. Frontend Behavior

### List screen

- Load page 1 with the default page size when the screen opens.
- Reset to page 1 whenever search or a filter changes.
- Debounce search input and send its trimmed value.
- Render `centers_count` separately from the maximum-three center preview.
- Do not display or infer center responsibility flags from `centers` yet.
- Treat `next` and `previous` as pagination state; do not construct those URLs
  by modifying them manually.

### Create form

- Require email, password confirmation, and at least one selected center.
- Present independent Admin and Care Staff toggles for every selected center.
- Prevent submission while any center has both toggles disabled.
- Prevent duplicate selected-center rows.
- Submit gender and title codes, not their display labels.
- Disable repeated submission while the request is pending.
- On success, close/reset the form and refetch `GET /associates/`.
- On a field validation error, keep the form state and display the backend
  message next to the relevant field or center selector.

## 8. Acceptance Criteria

- An administrator can page, search, and filter the associate collection.
- List results render the total center count and no more than three center
  preview entries.
- The frontend does not assume that center-preview entries contain assignment
  flags.
- The create form cannot submit without at least one center.
- Every submitted center has `is_admin=true`, `is_care_staff=true`, or both.
- The frontend prevents duplicate center selections, while remaining compatible
  with the backend's last-occurrence-wins behavior.
- Valid associate and center data produce a `201 Created` response.
- Invalid center IDs, invalid flag combinations, duplicate emails, and password
  errors are presented without losing the form state.
- After successful creation, the list is refetched and shows the created
  associate using authoritative server state.
