from django.db import models
from django.db.models.functions import Lower

from accounts.customers.utils.constants import AddressType
from accounts.users.models import AbstractUserProfile
from accounts.utils import get_user_model
from core.utils.fields import PhoneNumberField
from core.utils.models import BaseModel, BaseUUIDModel

User = get_user_model()


class Customer(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="customer",
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customers",
    )
    contact_email = models.EmailField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["contact_email", "user"],
                name="customer_email_idx",
                condition=models.Q(contact_email__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CustomerProfile(BaseUUIDModel, AbstractUserProfile):
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="profiles"
    )
    is_main = models.BooleanField(default=False, editable=False)
    is_onboarding_complete = models.BooleanField(default=False, editable=False)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customer_profiles",
    )

    centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    external_centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    emergency_contact_name = models.CharField(blank=True, default="", max_length=100)
    emergency_contact_phone = PhoneNumberField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                "customer",
                Lower("first_name"),
                Lower("last_name"),
                "gender",
                "date_of_birth",
                name="uniq_customer_profile",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(
                Lower("first_name"),
                Lower("last_name"),
                "gender",
                "date_of_birth",
                name="idx_customer_profile_lookup",
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CustomerCenterAssignment(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="customer_assignments"
    )

    is_primary = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customer_center_links",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile", "center"],
                name="uniq_customer_center",
            ),
            models.UniqueConstraint(
                fields=["customer_profile"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_center",
            ),
        ]
        verbose_name = "Customer-Center Assignment"

    def __str__(self):
        return f"{self.pk}"


class CustomerAssociateAssignment(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile, on_delete=models.CASCADE, related_name="associate_assignments"
    )
    associate = models.ForeignKey(
        "associates.Associate",
        on_delete=models.CASCADE,
        related_name="customer_assignments",
    )
    center = models.ForeignKey(
        "centers.Center",
        on_delete=models.CASCADE,
        related_name="customer_associate_assignments",
    )

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_customer_associate_links",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile", "associate", "center"],
                name="uniq_customer_associate_center",
            )
        ]
        verbose_name = "Customer-Associate Assignment"

    def __str__(self):
        return f"{self.pk}"


class CustomerProfileAddress(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    address_type = models.CharField(choices=AddressType, default=AddressType.OTHER)

    label = models.CharField(max_length=30, blank=True)
    line_1 = models.CharField(max_length=255)
    line_2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=255, blank=True)

    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=50)
    pincode = models.CharField(max_length=20)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile"],
                condition=models.Q(is_default=True),
                name="uniq_default_customer_profile_address",
            )
        ]

    def __str__(self):
        return f"{self.pk}"
