from django.db import models

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from products.models import Product
from test_kit_assignment.utils.constants import (
    TestKitAssignmentStatus,
    TestKitHandoverType,
)

User = get_user_model()


class TestKitAssignment(BaseUUIDModel):
    assigned_to = models.ForeignKey(
        CustomerProfile,
        on_delete=models.PROTECT,
        related_name="test_kit_assignments",
    )
    handover_type = models.CharField(
        max_length=32,
        choices=TestKitHandoverType.choices,
    )
    is_kit_journey_visible = models.BooleanField(default=True)
    clinic = models.ForeignKey(
        Center,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_kit_assignments",
    )
    assigned_on = models.DateTimeField()
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=TestKitAssignmentStatus.choices,
        default=TestKitAssignmentStatus.ACTIVE,
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_test_kit_assignments",
    )
    products = models.ManyToManyField(
        Product,
        related_name="test_kit_assignments",
    )

    class Meta:
        ordering = ["-assigned_on", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assigned_to"],
                condition=models.Q(status=TestKitAssignmentStatus.ACTIVE),
                name="uniq_active_test_kit_per_profile",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="testkit_status_created_idx",
            ),
            models.Index(
                fields=["assigned_on"],
                name="testkit_assigned_on_idx",
            ),
            models.Index(
                fields=["assigned_to"],
                name="testkit_assigned_to_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"
