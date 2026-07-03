from django.contrib.auth import get_user_model
from django.db import models
from django.utils.text import gettext_lazy as _

from accounts.notifications.utils.constants import NotificationType, NotificationProjectID
from core.utils.models import BaseUUIDModel

User = get_user_model()


class FirebaseRegistrationToken(BaseUUIDModel):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="firebase_registration_tokens"
    )
    ip_address = models.GenericIPAddressField(_("IP Address"))
    user_agent = models.CharField(max_length=300)
    project_id = models.CharField(max_length=30, db_index=True, choices=NotificationProjectID)
    token = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "user_agent", "ip_address", "project_id", "token"],
                name="unique_user_token",
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class UserNotification(BaseUUIDModel):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=120)
    body = models.TextField(null=True, blank=True)
    notification_type = models.CharField(
        max_length=50, db_index=True, choices=NotificationType
    )
    image = models.FileField(upload_to="users/notifications/", null=True, blank=True)
    project_id = models.CharField(max_length=30, db_index=True)
    firebase_message_id = models.CharField(max_length=255, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    data = models.JSONField(null=True, blank=True, default=dict, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
