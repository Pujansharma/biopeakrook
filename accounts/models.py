from django.contrib.auth import get_user_model
from django.db import models

from accounts.utils.constants import UserType, USER_TYPE_CHOICES
from core.utils.models import BaseModel

User = get_user_model()


class UserAccount(BaseModel):
    user = models.OneToOneField(
        User,
        related_name="account",
        on_delete=models.CASCADE,
        primary_key=True,
        db_index=True,
    )
    account_type = models.CharField(
        max_length=20, default=UserType.UNKNOWN, choices=USER_TYPE_CHOICES
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
