# TOTP — Two-Factor Authentication

## Overview

TOTP (Time-based One-Time Password) adds a second authentication factor to the standard email/password login. Users who enable TOTP must supply a 6-digit code from an authenticator app (Google Authenticator, Authy, etc.) after credentials are verified.

Phone OTP login is exempt from TOTP by design — phone possession is itself a second factor.

---

## Architecture

```
accounts/
├── verifications/
│   ├── models.py         # TOTPCredential, TOTPSession, TOTPRecoveryCode
│   └── utils/
│       └── __init__.py   # verify_two_factor_code, get_two_factor_uri, get_qr_code_data_uri
├── serializers.py        # LoginSerializer — branches on is_enrolled
└── urls.py               # auth/totp/verify/

accounts/users/
└── urls.py               # users/totp/ (self-service management)
```

`pyotp` handles all TOTP primitives. No external auth packages are used.

---

## Two-Phase Login Flow

```
POST /auth/login/  {email, password}
  │
  ├── TOTP not enrolled
  │     └── {is_mfa_required: false, access: <jwt>, refresh: <jwt>, totp_token: null}
  │                                                                  ← fully authenticated
  │
  └── TOTP enrolled
        └── {is_mfa_required: true, access: null, refresh: null, totp_token: <opaque>}
                    │
                    ▼
        POST /auth/totp/verify/  {totp_token, code}
          ├── invalid/expired token  → 400
          ├── incorrect code         → 400  (attempt counter incremented)
          ├── account locked         → 403
          └── valid
                └── {is_mfa_required: false, access: <jwt>, refresh: <jwt>, totp_token: null}
                                                             ← fully authenticated
```

### Response Structure

The login response shape is identical for all users. Fields with no significance in a given state are `null`.

| Field | Non-TOTP user | TOTP user (step 1) | TOTP user (step 2) |
|---|---|---|---|
| `is_mfa_required` | `false` | `true` | `false` |
| `access` | JWT | `null` | JWT |
| `refresh` | JWT | `null` | JWT |
| `totp_token` | `null` | opaque string | `null` |

The client checks `is_mfa_required`. If `true`, it holds the `totp_token`, prompts for the authenticator code, and posts to `/auth/totp/verify/`. On `false`, authentication is complete.

### LoginSerializer Branch

```python
def validate(self, attrs):
    user = authenticate(email=attrs['email'], password=attrs['password'])
    if not user:
        raise AuthenticationFailed(self.error_messages['no_active_account'])

    totp_credential = TOTPCredential.objects.filter(user=user, is_enrolled=True).first()
    if totp_credential:
        self.check_totp_lockout(totp_credential)
        return self.build_login_response(totp_enabled=True, totp_token=get_mfa_token_for_user(user))
    return self.build_login_response(tokens=perform_login_for_user(user))
```

---

## Models

### TOTPCredential

Stores the TOTP secret for an enrolled user. One row per user.

```python
class TOTPCredential(BaseModel):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name='totp_credential'
    )
    secret = models.TextField(editable=False)
    is_enrolled = models.BooleanField(default=False)   # True only after setup is confirmed
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    lock_expires_at = models.DateTimeField(null=True, blank=True)
    is_permanently_locked = models.BooleanField(default=False)
```

`is_enrolled=False` rows are created during setup (QR generation). Until the user verifies their first code, TOTP is not enforced at login. Calling setup again overwrites the pending secret — last write wins.

`is_enrolled` is the sole gate used at login. `failed_attempts`, `lock_expires_at`, and `is_permanently_locked` drive the lockout ladder.

### TOTPSession

Carries user identity between step 1 and step 2 of login. One row per user, updated on each login attempt.

```python
class TOTPSession(BaseModel):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name='totp_session'
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    # is_active inherited from BaseModel
```

Lifecycle:
- `update_or_create(user=user, defaults={token: uuid4().hex, expires_at: now+5min, is_active: True})` on step 1.
- Fetched by `token` on step 2, with `is_active=True` and `expires_at__gte=now()`.
- Marked `is_active=False` on successful verification. Never deleted.

Since this is OneToOne, accumulation is bounded by user count. Stale rows serve as an audit trail.

### TOTPRecoveryCode

One-time backup codes for account recovery when the authenticator app is unavailable.

```python
class TOTPRecoveryCode(BaseModel):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='recovery_codes'
    )
    code_hash = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
```

Recovery codes are generated at TOTP enrollment, returned **once** in plaintext, and stored only as `sha256(code)`. Even admins cannot recover the originals. If a user loses their codes, they regenerate — which invalidates all previous codes and creates a fresh set.

Verification: `sha256(submitted_code)` compared against `code_hash`. On match, `used_at` is set — a used code is never accepted again.

---

## Lockout

After 10 consecutive failed TOTP attempts, the account enters a progressive lockout.

```python
LOCKOUT_SCHEDULE = {
    10: timedelta(hours=1),
    11: timedelta(hours=2),
    12: timedelta(hours=3),
    13: timedelta(hours=6),
    14: timedelta(hours=8),
    15: timedelta(hours=12),
    16: timedelta(hours=24),
}
```

At `failed_attempts >= 17`, `is_permanently_locked` is set to `True`. The user must contact an admin to reset.

On each failed attempt:
1. Increment `failed_attempts`.
2. Look up `LOCKOUT_SCHEDULE.get(failed_attempts)`.
3. If a duration is returned, set `lock_expires_at = now() + duration`.
4. If no duration (permanent), set `is_permanently_locked = True`.

On successful verification:
- Reset `failed_attempts = 0`, `lock_expires_at = None`, `is_permanently_locked = False`.

Every verify attempt checks lockout state first:

```python
if totp_credential.is_permanently_locked:
    raise AuthenticationFailed('Account permanently locked. Contact support.')
if totp_credential.lock_expires_at and totp_credential.lock_expires_at > timezone.now():
    raise AuthenticationFailed('Account temporarily locked. Try again later.')
```

---

## URLs

```
auth/totp/verify/       POST  — unauthenticated, step 2 of login
users/totp/             GET   — setup (generate QR + secret)
                        POST  — {action: 'enable'|'disable', code: ...}
```

`auth/totp/verify/` carries no `permission_classes`. Identity comes from the `totp_token` field in the request body, not from a Bearer token. The view validates the session record directly.

`users/totp/` requires `IsAuthenticated`. `request.user` is the sole identity source — no user ID in the path.

### Admin TOTP Management

Admin-side unlock or forced removal of a user's TOTP is handled under the scoped associate/customer routes when needed:

```
associates/<pk>/totp/   DELETE  — admin force-removes TOTPCredential, resets lockout
customers/<pk>/totp/    DELETE  — same for customers
```

---

## Self-Service Management

### Setup — `GET users/totp/`

1. If `TOTPCredential` exists with `is_enrolled=True` → 400 "TOTP already enabled."
2. `update_or_create(user=request.user, defaults={secret: get_secret(), is_enrolled: False})`
3. Return:

```json
{
  "secret": "BASE32SECRET",
  "qr_code": "data:image/png;base64,..."
}
```

The user scans the QR in their authenticator app. The setup is not active until confirmed via `enable`.

### Enable — `POST users/totp/` `{action: "enable", code: "123456"}`

1. Fetch `TOTPCredential` for `request.user` where `is_enrolled=False`.
2. `verify_two_factor_code(secret, code)` with `valid_window=1`.
3. On success: `is_enrolled=True`.
4. Generate 10 recovery codes, store hashed, return plaintext once.

### Disable — `POST users/totp/` `{action: "disable", code: "123456"}`

1. Fetch `TOTPCredential` for `request.user` where `is_enrolled=True`.
2. `verify_two_factor_code(secret, code)`.
3. On success: set `is_enrolled=False`, clear `failed_attempts`, `lock_expires_at`, `is_permanently_locked`.
4. Delete all `TOTPRecoveryCode` rows for the user.

TOTP is now inactive. The secret is retained in case the user re-enables without going through setup again. Call `setup` to rotate the secret.

---

## Security Notes

### Phone OTP Exemption

Users authenticating via phone OTP (`/auth/login-otp/`) skip TOTP entirely. Phone possession is already a second factor. This is a permanent design decision and not a bypass.

### Replay Prevention

`TOTPSession.is_active` is set to `False` immediately on successful verification. A replayed `totp_token` within its 5-minute window is rejected.

`pyotp` is called with `valid_window=1` — it accepts codes from the previous and next 30-second window to tolerate clock drift. Without this, borderline codes fail silently.

### Time-Based Code Replay

Within a 30-second TOTP window, the same code can be submitted more than once. If this is a concern, store `last_used_counter` on `TOTPCredential` (derived from `int(time.time() // 30)`) and reject codes with a counter `<=` the stored value.

### Recovery Code Entropy

Each recovery code is `uuid4().hex[:10]` — 40 bits of entropy. Generate 10 codes per enrollment. Codes are single-use and invalidated as a set on regeneration.

---

*Last updated: April 2026*