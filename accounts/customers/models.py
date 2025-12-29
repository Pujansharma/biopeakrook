from django.db import models

from accounts.utils import get_user_model
from core.utils.models import BaseModel

User = get_user_model()


class Customer(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name='customer',
        db_index=True
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.PROTECT, related_name='customers',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"
