from django.core.validators import MinValueValidator
from django.db import models

from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from products.models import Product, Provider

User = get_user_model()


class ProductInventoryBatch(BaseUUIDModel):
    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, related_name="inventory_batches"
    )
    received_on = models.DateField()
    batch_id = models.CharField(max_length=32, unique=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_product_inventory_batches",
    )

    class Meta:
        ordering = ["-received_on", "-created_at"]
        indexes = [
            models.Index(fields=["provider", "received_on"], name="prodinv_batch_prov_dt_idx"),
            models.Index(fields=["received_on", "created_at"], name="prodinv_batch_recv_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class ProductInventoryBatchItem(BaseUUIDModel):
    batch = models.ForeignKey(
        ProductInventoryBatch, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="inventory_batch_items"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    qc_ack_packaging = models.BooleanField(default=True)
    qc_ack_all_components = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_product_inventory_batch_items",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "product"],
                name="unique_product_inventory_batch_item",
            )
        ]
        indexes = [
            models.Index(fields=["product", "created_at"], name="prodinv_item_prod_created_idx"),
            models.Index(fields=["batch", "product"], name="prodinv_item_batch_prod_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"
