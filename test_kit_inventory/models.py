from django.core.validators import MinValueValidator
from django.db import models

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from products.models import Product, Provider
from test_kit_inventory.utils.constants import (
    TestKitAssignmentStatus,
    TestKitHandoverType,
)

User = get_user_model()


class TestKitInventoryBatch(BaseUUIDModel):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="test_kit_inventory_batches",
    )
    received_on = models.DateField()
    batch_id = models.CharField(max_length=32, unique=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_test_kit_inventory_batches",
    )

    class Meta:
        ordering = ["-received_on", "-created_at"]
        indexes = [
            models.Index(fields=["provider", "received_on"], name="tkinv_batch_prov_dt_idx"),
            models.Index(fields=["received_on", "created_at"], name="tkinv_batch_recv_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class TestKitInventoryBatchItem(BaseUUIDModel):
    batch = models.ForeignKey(
        TestKitInventoryBatch,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="test_kit_inventory_batch_items",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    qc_ack_packaging = models.BooleanField(default=True)
    qc_ack_all_components = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_test_kit_inventory_batch_items",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "product"],
                name="unique_test_kit_inventory_batch_item",
            )
        ]
        indexes = [
            models.Index(fields=["product", "created_at"], name="tkinv_item_prod_created_idx"),
            models.Index(fields=["batch", "product"], name="tkinv_item_batch_prod_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class TestKitProvider(BaseUUIDModel):
    provider = models.OneToOneField(
        Provider,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="test_kit_provider",
    )
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name", "-created_at"]

    def __str__(self) -> str:
        return self.name


class TestKitProduct(BaseUUIDModel):
    provider = models.ForeignKey(
        TestKitProvider,
        on_delete=models.PROTECT,
        related_name="test_kit_products",
    )
    test_name = models.CharField(max_length=200)
    code = models.CharField(max_length=32, unique=True, db_index=True)

    class Meta:
        ordering = ["test_name", "-created_at"]
        indexes = [
            models.Index(fields=["provider", "test_name"], name="tkinv_prod_prov_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.test_name}"


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
                name="uniq_tkinv_actv_kit_prof",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="tkinv_asgn_stat_crt_idx",
            ),
            models.Index(
                fields=["assigned_on"],
                name="tkinv_asgn_on_idx",
            ),
            models.Index(
                fields=["assigned_to"],
                name="tkinv_asgn_to_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"
