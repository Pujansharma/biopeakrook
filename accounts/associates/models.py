from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from accounts.associates.utils.constants import (
    AssociateRoleFeature,
    AssociateRoleTag,
    AssociateRoleAbility,
    AssociateTitle,
)
from accounts.utils import get_user_model
from core.utils.constants import AppointmentModes
from core.utils.fields import PhoneNumberField
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

    is_external = models.BooleanField(
        _("External Role"),
        default=False,
        help_text=_(
            "If enabled, this role can be assigned to external associates (not employed directly by any center)."
        ),
    )
    is_system = models.BooleanField(
        _("System Role"),
        default=False,
        editable=False,
        help_text=_(
            "System roles are platform-defined and available across all centers by default. They cannot be edited."
        ),
    )

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_associate_roles",
    )

    summary = models.JSONField(default=dict, editable=False)
    date_joined = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["features", "is_system"],
                condition=Q(is_system=True),
                name="uniq_system_role",
            ),
            models.UniqueConstraint(
                "center",
                Lower("name"),
                condition=Q(center__isnull=False),
                name="uniq_associate_role_center_name",
            ),
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
    contact_phone = PhoneNumberField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    title = models.CharField(choices=AssociateTitle, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tagline = models.CharField(max_length=100, null=True, blank=True)
    experience = models.FloatField(
        null=True, blank=True, help_text=_("Years of experience")
    )

    qualifications = ArrayField(
        base_field=models.CharField(max_length=50), max_length=2, default=list
    )
    professions = ArrayField(
        base_field=models.CharField(max_length=50), max_length=2, default=list
    )
    has_verified_badge = models.BooleanField(default=False)
    centers_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "contact_phone"],
                name="associate_contact_phone_idx",
                condition=models.Q(contact_phone__isnull=False),
            ),
            models.Index(
                fields=["contact_phone"],
                name="assoc_phone_search_idx",
                condition=models.Q(contact_phone__isnull=False),
            ),
        ]

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

    # Center-specific configuration
    mode = models.CharField(
        choices=AppointmentModes,
        help_text="How this associate works at THIS center (virtual/in-person/both)",
        default=AppointmentModes.BOTH,
    )

    # Is this their primary center?
    is_primary = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_care_staff = models.BooleanField(default=False)

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
            ),
            # models.CheckConstraint(
            #     name="associate_admin_or_staff",
            #     condition=models.Q(is_admin=True) | models.Q(is_care_staff=True),
            # )
        ]
        verbose_name = "Associate-Center Assignment"

    def __str__(self):
        return f"{self.pk}"


class AssociateCenterAssignmentRole(BaseUUIDModel):
    """Through table: many care roles per associate×center assignment."""

    assignment = models.ForeignKey(
        AssociateCenterAssignment,
        on_delete=models.CASCADE,
        related_name="role_links",
    )
    role = models.ForeignKey(
        AssociateRole,
        on_delete=models.PROTECT,
        related_name="assignment_role_links",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "role"],
                name="uniq_assignment_role_link",
            )
        ]

    def __str__(self):
        return f"{self.pk}"
