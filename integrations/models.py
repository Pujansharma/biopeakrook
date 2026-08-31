from django.contrib.postgres.fields import ArrayField
from django.db import models
from core.utils.models import BaseUUIDModel


class GoogleCalendarConnection(BaseUUIDModel):
    associate = models.OneToOneField(
        "associates.Associate",
        on_delete=models.CASCADE,
        related_name="google_calendar_connection",
    )
    google_email = models.EmailField(unique=True)

    # Encrypted at rest, see integrations.google_calendar.utils.encrypt/decrypt.
    access_token = models.TextField()
    refresh_token = models.TextField()
    access_token_expires_at = models.DateTimeField(null=True, blank=True)

    # Incremental sync/push notifications (Google Calendar watch channel).
    sync_token = models.CharField(max_length=255, blank=True)
    watch_channel_id = models.CharField(max_length=255, blank=True)
    watch_channel_expiration = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class GoogleCalendarEvent(BaseUUIDModel):
    """
    One row per appointments.Appointment that has been mirrored onto Google
    Calendar. Only stores what Google adds on top of the existing Appointment
    row (title/start/end/notes/location already live there), no duplicated
    fields, so there's one place to edit an appointment, not two.
    """

    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="google_calendar_event",
    )

    google_event_id = models.CharField(max_length=255, db_index=True)
    meet_link = models.URLField(blank=True)

    participant_emails = ArrayField(
        base_field=models.EmailField(), default=list, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
