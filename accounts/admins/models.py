from django.db import models

from accounts.utils import get_user_model
from core.utils.models import BaseModel

User = get_user_model()


class Admin(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='admin', db_index=True, primary_key=True
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name='created_admins'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"
