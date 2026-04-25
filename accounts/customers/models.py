from django.db import models
from django.db.models.functions import Lower

from accounts.users.models import AbstractUserProfile
from accounts.utils import get_user_model
from core.utils.models import BaseModel, BaseUUIDModel

User = get_user_model()


class Customer(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name='customer',
        db_index=True
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_customers'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class CustomerProfile(BaseUUIDModel, AbstractUserProfile):
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='profiles'
    )
    is_primary = models.BooleanField(default=False, editable=False)
    is_onboarding_complete = models.BooleanField(default=False, editable=False)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_customer_profiles'
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                'customer', Lower('first_name'), Lower('last_name'), 'gender', 'date_of_birth',
                name='uniq_customer_profile',
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(
                Lower('first_name'), Lower('last_name'),
                'gender', 'date_of_birth', name='idx_customer_profile_lookup'
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CustomerCenterAssignment(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile, on_delete=models.CASCADE, related_name='center_assignments'
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='customer_assignments'
    )

    is_primary = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_customer_center_links'
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer_profile', 'center'], name='uniq_customer_center'
            )
        ]
        verbose_name = "Customer-Center Assignment"

    def __str__(self):
        return f"{self.pk}"


class CustomerAssociateAssignment(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile, on_delete=models.CASCADE, related_name='associate_assignments'
    )
    associate = models.ForeignKey(
        'associates.Associate', on_delete=models.CASCADE, related_name='customer_assignments'
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='customer_associate_assignments'
    )

    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_customer_associate_links'
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer_profile', 'associate', 'center'],
                name='uniq_customer_associate_center'
            )
        ]
        verbose_name = "Customer-Associate Assignment"

    def __str__(self):
        return f"{self.pk}"
