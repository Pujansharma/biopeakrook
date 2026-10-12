from django.db import models


class CommunicationChannel(models.TextChoices):
    WHATSAPP = "whatsapp", "WhatsApp"
    GOOGLE_CALENDAR = "google_calendar", "Google Calendar"


class CommunicationEventType(models.TextChoices):
    APPOINTMENT_CONFIRMED = "appointment_confirmed", "Appointment Confirmed"
    APPOINTMENT_CANCELLED = "appointment_cancelled", "Appointment Cancelled"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled", "Appointment Rescheduled"
    APPOINTMENT_REMINDER = "appointment_reminder", "Appointment Reminder"
    APPOINTMENT_NO_SHOW = "appointment_no_show", "Appointment No Show"
    ASSOCIATE_BLOCK_SYNC = "associate_block_sync", "Associate Block Sync"
    ASSOCIATE_LEAVE_SYNC = "associate_leave_sync", "Associate Leave Sync"


class CommunicationOutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENDING = "sending", "Sending"
    ACCEPTED = "accepted", "Accepted"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


# Once-per-appointment WhatsApp/Google terminal events (partial unique).
TERMINAL_APPOINTMENT_EVENT_TYPES = (
    CommunicationEventType.APPOINTMENT_CONFIRMED,
    CommunicationEventType.APPOINTMENT_CANCELLED,
    CommunicationEventType.APPOINTMENT_REMINDER,
    CommunicationEventType.APPOINTMENT_NO_SHOW,
)

# Statuses that block a second terminal outbox row (FAILED still retrying).
TERMINAL_OUTBOX_BLOCKING_STATUSES = (
    CommunicationOutboxStatus.PENDING,
    CommunicationOutboxStatus.SENDING,
    CommunicationOutboxStatus.ACCEPTED,
    CommunicationOutboxStatus.SENT,
    CommunicationOutboxStatus.DELIVERED,
    CommunicationOutboxStatus.READ,
    CommunicationOutboxStatus.FAILED,
)

# Meta-approved WhatsApp template names (not env-driven).
WHATSAPP_TEMPLATE_BY_EVENT = {
    CommunicationEventType.APPOINTMENT_CONFIRMED: "appointment_confirmed_template",
    CommunicationEventType.APPOINTMENT_CANCELLED: "appointment_cancelled_template",
    CommunicationEventType.APPOINTMENT_RESCHEDULED: "appointment_rescheduled_template",
    CommunicationEventType.APPOINTMENT_REMINDER: "therapy_session_reminder",
    CommunicationEventType.APPOINTMENT_NO_SHOW: "therapy_session_no_show",
}


class AppDownloadPlatform(models.TextChoices):
    ANDROID = "android", "Android"
    IOS = "ios", "iOS"
    OTHER = "other", "Other"


class AppDownloadEntry(models.TextChoices):
    """How the hit reached store redirect / chooser (QR URL unchanged)."""

    UA = "ua", "UA redirect"
    CHOOSER = "chooser", "Chooser page"
    PLATFORM_QUERY = "platform_query", "Chooser store badge"


PLAY_STORE_URL = (
    "https://play.google.com/store/apps/details?id=com.biopeak.healthapp"
)
APP_STORE_URL = "https://apps.apple.com/app/biopeak/id6759485756"

APP_DOWNLOAD_DESTINATION_BY_PLATFORM = {
    AppDownloadPlatform.ANDROID: PLAY_STORE_URL,
    AppDownloadPlatform.IOS: APP_STORE_URL,
}

APP_DOWNLOAD_USER_AGENT_MAX_LENGTH = 512
APP_DOWNLOAD_CHOOSER_TEMPLATE = "app_download/Biopeak_App_Download.html"

# Case-insensitive; `\bbot\b` avoids matching "both". Skip click insert only.
APP_DOWNLOAD_BOT_USER_AGENT_PATTERN = (
    r"("
    r"\bbot\b|spider|crawl|slurp|"
    r"facebookexternalhit|twitterbot|linkedinbot|discordbot|"
    r"googlebot|bingbot|yandex|baiduspider|duckduckbot|"
    r"semrush|ahrefs|mj12bot|dotbot|petalbot|bytespider|"
    r"slackbot|applebot|embedly|outbrain"
    r")"
)
