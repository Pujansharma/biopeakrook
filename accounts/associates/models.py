from django.contrib.postgres.fields import ArrayField
from django.db import models

from accounts.associates.utils.constants import (
    AssociateRoleFeature,
    AssociateRoleTag,
    AssociateRoleAbility,
)
from accounts.utils import get_user_model
from appointments.utils.constants import ScheduleModes
from core.utils.models import BaseModel, BaseUUIDModel

User = get_user_model()


class AssociateRole(BaseUUIDModel):
    name = models.CharField(max_length=50)
    features = ArrayField(
        base_field=models.CharField(
            choices=AssociateRoleFeature.CHOICES, default=AssociateRoleFeature.ALL
        ),
        default=list,
    )

    center = models.ForeignKey(
        "centers.Center",
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,
        blank=True,
    )

    role_tag = models.CharField(
        choices=AssociateRoleTag, default=AssociateRoleTag.CLINICAL
    )

    is_external = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False, editable=False)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_associate_roles",
    )

    summary = models.JSONField(default=dict, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["features", "is_system"],
                condition=models.Q(is_system=True),
                name="uniq_system_role",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.pk})"


class AssociateRolePermission(BaseUUIDModel):
    role = models.ForeignKey(
        AssociateRole, related_name="permissions", on_delete=models.CASCADE
    )
    feature = models.CharField(choices=AssociateRoleFeature.CHOICES)
    ability = models.CharField(choices=AssociateRoleAbility.CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "feature"], name="uniq_role_feature"
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class Associate(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        db_index=True,
        related_name="associate",
    )

    is_external = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_associates",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class AssociateCenterAssignment(BaseUUIDModel):
    """Links associates to centers with center-specific config"""

    associate = models.ForeignKey(
        Associate, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="associate_assignments"
    )

    role = models.ForeignKey(
        AssociateRole,
        related_name="role_assignments",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Center-specific configuration
    mode = models.CharField(
        choices=ScheduleModes,
        help_text="How this associate works at THIS center (virtual/in-person/both)",
        default=ScheduleModes.BOTH,
    )

    # Is this their primary center?
    is_primary = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_associations",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["associate", "center"], name="uniq_associate_center"
            )
        ]
        verbose_name = "Associate-Center Assignment"

    def __str__(self):
        return f"{self.pk}"
