from django.db import models


class CommunicationChannel(models.TextChoices):
    WHATSAPP = "whatsapp", "WhatsApp"
    GOOGLE_CALENDAR = "google_calendar", "Google Calendar"


class CommunicationEventType(models.TextChoices):
    APPOINTMENT_CONFIRMED = "appointment_confirmed", "Appointment Confirmed"
    APPOINTMENT_CANCELLED = "appointment_cancelled", "Appointment Cancelled"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled", "Appointment Rescheduled"
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
