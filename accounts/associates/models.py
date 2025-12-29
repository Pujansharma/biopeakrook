from django.contrib.postgres.fields import ArrayField
from django.db import models

from accounts.associates.utils.constants import SpecializationType, SpecializationRole
from accounts.utils import get_user_model
from appointments.utils.constants import ScheduleModes
from core.utils.models import BaseModel, BaseUUIDModel

User = get_user_model()


class Associate(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, db_index=True, related_name='associate'
    )

    specializations = ArrayField(
        base_field=models.CharField(choices=SpecializationType.CHOICES),
        max_length=len(SpecializationType.CHOICES),
    )
    role = models.CharField(choices=SpecializationRole.CHOICES)

    is_admin = models.BooleanField(default=False)
    is_external = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class AssociateCenterAssignment(BaseUUIDModel):
    """Links associates to centers with center-specific config"""
    associate = models.ForeignKey(
        Associate, on_delete=models.CASCADE, related_name='center_assignments'
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='associate_assignments'
    )

    # Center-specific configuration
    mode = models.CharField(
        choices=ScheduleModes.CHOICES,
        help_text="How this associate works at THIS center (virtual/in-person/both)"
    )

    # Is this their primary center?
    is_primary = models.BooleanField(default=False)

    # Active status per center
    is_active = models.BooleanField(default=True)

    # Effective dates
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['associate', 'center'], name='uniq_associate_center')
        ]
        verbose_name = "Associate-Center Assignment"

    def __str__(self):
        return f"{self.pk}"
