from django.db import models

from accounts.audits.utils.constants import AuditAction
from accounts.centers.models import Center
from accounts.utils import get_user_model
from accounts.utils.constants import USER_TYPE_CHOICES, UserType
from core.utils.models import BaseUUIDModel

User = get_user_model()


class AuditLog(BaseUUIDModel):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="audit_logs"
    )
    user_type = models.CharField(
        max_length=20, choices=USER_TYPE_CHOICES, default=UserType.UNKNOWN
    )
    action = models.CharField(max_length=10, choices=AuditAction.CHOICES)

    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField(null=True, blank=True)

    center = models.ForeignKey(
        Center,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["user", "action"]),
        ]

    def __str__(self):
        return f"{self.user_type}:{self.action}:{self.entity_type}"
