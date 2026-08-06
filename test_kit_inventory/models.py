from django.core.validators import MinValueValidator
from django.db import models

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from products.models import Product as CatalogProduct, Provider as CatalogProvider
from test_kit_inventory.utils.constants import (
    TestKitAssignmentStatus,
    TestKitHandoverType,
)

User = get_user_model()


class Provider(BaseUUIDModel):
    provider = models.OneToOneField(
        CatalogProvider,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="test_kit_inventory_provider",
    )
    name = models.CharField(max_length=200)

    class Meta:
        db_table = "test_kit_inventory_provider"
        ordering = ["name", "-created_at"]

    def __str__(self) -> str:
        return self.name


class Product(BaseUUIDModel):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="products",
    )
    test_name = models.CharField(max_length=200)
    code = models.CharField(max_length=32, unique=True, db_index=True)
    is_assignable = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "test_kit_inventory_product"
        ordering = ["test_name", "-created_at"]
        indexes = [
            models.Index(fields=["provider", "test_name"], name="tkinv_prod_prov_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.test_name}"


class Batch(BaseUUIDModel):
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="batches",
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
        db_table = "test_kit_inventory_batch"
        ordering = ["-received_on", "-created_at"]
        indexes = [
            models.Index(fields=["provider", "received_on"], name="tkinv_batch_prov_dt_idx"),
            models.Index(fields=["received_on", "created_at"], name="tkinv_batch_recv_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class Item(BaseUUIDModel):
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="batch_items",
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
        db_table = "test_kit_inventory_item"
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


class Assignment(BaseUUIDModel):
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
        related_name="assignments",
        db_table="test_kit_inventory_assignment_product",
    )

    class Meta:
        db_table = "test_kit_inventory_assignment"
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
