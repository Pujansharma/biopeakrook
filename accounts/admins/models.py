from django.db import models

from accounts.utils import get_user_model
from core.utils.fields import PhoneNumberField
from core.utils.models import BaseModel

User = get_user_model()


class Admin(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="admin",
        db_index=True,
        primary_key=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="created_admins",
    )
    contact_phone = PhoneNumberField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "contact_phone"],
                name="admin_contact_phone_idx",
                condition=models.Q(contact_phone__isnull=False),
            ),
            models.Index(
                fields=["contact_phone"],
                name="admin_contact_phone_search_idx",
                condition=models.Q(contact_phone__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.pk}"
