from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.customers.models import CustomerProfile
from core.utils.models import BaseModel


class MetsightsProfile(BaseModel):
    customer_profile = models.OneToOneField(
        CustomerProfile, primary_key=True, related_name='metsights_profile',
        on_delete=models.CASCADE, db_index=True
    )
    profile_id = models.CharField(_("Metsights Profile ID"), max_length=80, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.pk}"
