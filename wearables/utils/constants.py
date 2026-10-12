from django.db import models


class WearableSource(models.TextChoices):
    APPLE_HEALTH = "Apple Health", "Apple Health"
    HEALTH_CONNECT = "Health Connect", "Health Connect"
    SAMSUNG_HEALTH = "Samsung Health", "Samsung Health"
    GARMIN = "Garmin", "Garmin"
    FITBIT = "Fitbit", "Fitbit"
    OURA = "Oura", "Oura"
    POLAR = "Polar", "Polar"
    WITHINGS = "Withings", "Withings"
    WHOOP = "Whoop", "Whoop"
    DEXCOM = "Dexcom", "Dexcom"


API_WEARABLE_SOURCES = {
    WearableSource.GARMIN,
    WearableSource.FITBIT,
    WearableSource.OURA,
    WearableSource.POLAR,
    WearableSource.WITHINGS,
    WearableSource.WHOOP,
    WearableSource.DEXCOM,
}

NATIVE_WEARABLE_SOURCES = {
    WearableSource.APPLE_HEALTH,
    WearableSource.HEALTH_CONNECT,
    WearableSource.SAMSUNG_HEALTH,
}


class ConnectionMethod(models.TextChoices):
    API = "api", "API authorization"
    SDK = "sdk", "Native SDK"


class ConnectionStatus(models.TextChoices):
    NEVER_CONNECTED = "never_connected", "Never connected"
    CONNECTING = "connecting", "Connecting"
    AUTHORIZING = "authorizing", "Authorizing"
    PERMISSION_DENIED = "permission_denied", "Permission denied"
    IMPORTING = "connected_importing", "Connected — importing"
    ACTIVE = "connected_active", "Connected — active"
    PARTIAL = "connected_partial", "Connected — partial"
    IDLE = "connected_idle", "Connected — idle"
    AUTHORIZATION_EXPIRED = "authorization_expired", "Authorization expired"
    DISCONNECTED = "disconnected", "Disconnected"
    RECONNECTED = "reconnected", "Reconnected"
    HISTORICAL_REIMPORT = "historical_reimport", "Historical re-import"
    PROVIDER_ERROR = "provider_error", "Provider error"


class AuthorizationStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    PENDING = "pending", "Pending"
    AUTHORIZED = "authorized", "Authorized"
    DENIED = "denied", "Denied"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"
    ERROR = "error", "Error"


class PermissionStatus(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    NOT_DETERMINED = "not_determined", "Not determined"
    GRANTED = "granted", "Granted"
    LIMITED = "limited", "Limited"
    DENIED = "denied", "Denied"


class HistoricalImportStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    RUNNING = "running", "Running"
    PARTIAL = "partial", "Partial"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class HealthDomain(models.TextChoices):
    SLEEP = "sleep", "Sleep"
    ACTIVITY = "activity", "Activity"
    HEART = "heart", "Heart"
    RECOVERY = "recovery", "Recovery"
    BODY = "body", "Body"
    WORKOUTS = "workouts", "Workouts"


HEALTH_DOMAIN_ORDER = [
    HealthDomain.SLEEP,
    HealthDomain.ACTIVITY,
    HealthDomain.HEART,
    HealthDomain.RECOVERY,
    HealthDomain.BODY,
    HealthDomain.WORKOUTS,
]


class HealthCardState(models.TextChoices):
    LOADING = "loading", "Loading"
    HISTORICAL_IMPORT_RUNNING = (
        "historical_import_running",
        "Historical Import Running",
    )
    HISTORICAL_IMPORT_PARTIAL = (
        "historical_import_partial",
        "Historical Import Partial",
    )
    HISTORICAL_IMPORT_FAILED = (
        "historical_import_failed",
        "Historical Import Failed",
    )
    AVAILABLE = "available", "Available"
    CURRENT_VALUE_ONLY = "current_value_only", "Current-Value-Only"
    TREND_AVAILABLE = "trend_available", "Trend-Available"
    WAITING_FOR_DATA = "waiting_for_data", "Waiting for Data"
    PERMISSION_REQUIRED = "permission_required", "Permission Required"
    UNSUPPORTED = "unsupported", "Unsupported"
    NO_DATA = "no_data", "No Data (No Measurements)"
    DISCONNECTED = "disconnected", "Disconnected"
    PROVIDER_ERROR = "provider_error", "Provider Error"
    AUTHORIZATION_EXPIRED = "authorization_expired", "Authorization Expired"
    SYNC_DELAYED = "sync_delayed", "Sync Delayed"
    HISTORICAL_GAP = "historical_gap", "Historical Gap"


class TrendDirection(models.TextChoices):
    IMPROVING = "improving", "Improving"
    STABLE = "stable", "Stable"
    DECLINING = "declining", "Declining"
    INSUFFICIENT_DATA = "insufficient_data", "Insufficient Data"
    UNKNOWN = "unknown", "Unknown"


class ConfidenceLevel(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"
    UNKNOWN = "unknown", "Unknown"


class DocumentStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    QUEUED = "queued", "Queued"
    PROCESSED = "processed", "Processed"
    DUPLICATE = "duplicate", "Duplicate"
    REJECTED = "rejected", "Rejected"
    FAILED = "failed", "Failed"


class HealthJobType(models.TextChoices):
    NORMALIZE_DOCUMENT = "normalize_document", "Normalize document"
    REFRESH_ANALYTICS = "refresh_analytics", "Refresh analytics"
    REFRESH_CONNECTION = "refresh_connection", "Refresh connection"
    REVOKE_CONNECTION = "revoke_connection", "Revoke connection"
    RECOVERY_PULL = "recovery_pull", "ROOK recovery pull"
    FRESHNESS_CHECK = "freshness_check", "Freshness check"


class HealthJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ConsentStatus(models.TextChoices):
    GRANTED = "granted", "Granted"
    REVOKED = "revoked", "Revoked"


class PreferredUnits(models.TextChoices):
    METRIC = "metric", "Metric"
    IMPERIAL = "imperial", "Imperial"


ALGORITHM_VERSION = "wearables-v1.0"

HEADLINE_METRICS = {
    HealthDomain.SLEEP: ["sleep_duration_seconds"],
    HealthDomain.ACTIVITY: ["steps"],
    HealthDomain.HEART: ["resting_heart_rate", "average_heart_rate"],
    HealthDomain.RECOVERY: [
        "recovery_score",
        "readiness_score",
        "stress_level",
    ],
    HealthDomain.BODY: ["weight_kg"],
    HealthDomain.WORKOUTS: ["workout_count"],
}

DOMAIN_TITLES = {
    HealthDomain.SLEEP: "Sleep",
    HealthDomain.ACTIVITY: "Activity",
    HealthDomain.HEART: "Heart",
    HealthDomain.RECOVERY: "Recovery",
    HealthDomain.BODY: "Body",
    HealthDomain.WORKOUTS: "Workouts",
}

DOMAIN_DEFAULT_UNITS = {
    HealthDomain.SLEEP: "hours",
    HealthDomain.ACTIVITY: "steps",
    HealthDomain.HEART: "bpm",
    HealthDomain.RECOVERY: "score",
    HealthDomain.BODY: "kg",
    HealthDomain.WORKOUTS: "sessions",
}

MINIMUM_MEANINGFUL_CHANGE = {
    "sleep_duration_seconds": 1800.0,
    "steps": 1000.0,
    "resting_heart_rate": 3.0,
    "average_heart_rate": 3.0,
    "hrv_rmssd": 5.0,
    "recovery_score": 5.0,
    "readiness_score": 5.0,
    "stress_level": 5.0,
    "weight_kg": 0.5,
    "workout_count": 1.0,
}

LOWER_IS_BETTER_METRICS = {
    "resting_heart_rate",
    "average_heart_rate",
    "stress_level",
}

