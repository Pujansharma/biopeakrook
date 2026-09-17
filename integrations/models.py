from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from accounts.utils import get_user_model
from core.utils.models import BaseModel, BaseUUIDModel
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
)

User = get_user_model()


class GoogleCalendarConnection(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="google_calendar_connection",
        primary_key=True,
        db_index=True,
    )
    google_email = models.EmailField(null=True, blank=True)
    google_access_token = models.TextField(null=True, blank=True)
    google_refresh_token = models.TextField(null=True, blank=True)
    google_access_token_expires_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("google_email"),
                name="uniq_google_calendar_connection_email",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CommunicationOutbox(BaseUUIDModel):
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="communication_messages",
    )
    channel = models.CharField(
        max_length=32,
        choices=CommunicationChannel,
        default=CommunicationChannel.WHATSAPP,
    )
    event_type = models.CharField(max_length=64, choices=CommunicationEventType)
    to_phone = models.CharField(max_length=32, blank=True)
    template_name = models.CharField(max_length=128, blank=True)
    template_language = models.CharField(max_length=16, blank=True)
    template_parameters = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=32,
        choices=CommunicationOutboxStatus,
        default=CommunicationOutboxStatus.PENDING,
        db_index=True,
    )
    wamid = models.CharField(max_length=255, blank=True, db_index=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_detail = models.TextField(blank=True)
    provider_response = models.JSONField(null=True, blank=True)
    skip_reason = models.CharField(max_length=255, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["appointment", "event_type"]),
            models.Index(
                fields=["appointment", "channel", "status"],
                name="integration_appt_chan_stat_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "channel", "event_type"],
                condition=Q(
                    event_type__in=[
                        CommunicationEventType.APPOINTMENT_CONFIRMED,
                        CommunicationEventType.APPOINTMENT_CANCELLED,
                    ],
                    status__in=[
                        CommunicationOutboxStatus.PENDING,
                        CommunicationOutboxStatus.SENDING,
                        CommunicationOutboxStatus.ACCEPTED,
                        CommunicationOutboxStatus.SENT,
                        CommunicationOutboxStatus.DELIVERED,
                        CommunicationOutboxStatus.READ,
                    ],
                ),
                name="uniq_comm_outbox_appointment_channel_terminal_event",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CommunicationWebhookEvent(BaseUUIDModel):
    """Idempotency log for Meta WhatsApp status / inbound webhooks."""

    event_key = models.CharField(max_length=255, unique=True)
    wamid = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=32, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
