from django.db import models

from accounts.customers.models import CustomerProfile
from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from diagnostics_orders.utils.constants import DiagnosticOrderStatus

User = get_user_model()


class CatalogItem(BaseUUIDModel):
    test_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_custom_package = models.BooleanField(default=False)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "diagnostics_orders_catalog_item"
        ordering = ["name", "-created_at"]

    def __str__(self):
        return f"{self.test_id} — {self.name}"


class DiagnosticOrder(BaseUUIDModel):
    request_id = models.CharField(max_length=128, unique=True, db_index=True)
    token = models.CharField(max_length=512)
    status = models.CharField(
        max_length=32,
        choices=DiagnosticOrderStatus.choices,
        default=DiagnosticOrderStatus.ORDER_CREATED,
        db_index=True,
    )
    address = models.TextField()
    pincode = models.CharField(max_length=20, blank=True, default="")
    slot_datetime = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True, default="")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    tat_in_hours = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_diagnostic_orders",
    )
    idempotency_key = models.CharField(
        max_length=128, unique=True, null=True, blank=True
    )
    raw_create_response = models.JSONField(default=dict, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    cancel_explanation = models.TextField(blank=True, default="")
    last_reschedule_reason = models.CharField(max_length=255, blank=True, default="")
    last_reschedule_explanation = models.TextField(blank=True, default="")
    reports = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "diagnostics_orders_order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "slot_datetime"], name="diag_ord_status_slot_idx"),
        ]

    def __str__(self):
        return self.request_id


class DiagnosticOrderCustomer(BaseUUIDModel):
    order = models.ForeignKey(
        DiagnosticOrder,
        on_delete=models.CASCADE,
        related_name="customers",
    )
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.PROTECT,
        related_name="diagnostic_order_customers",
    )
    name = models.CharField(max_length=255)
    gender = models.CharField(max_length=16, blank=True, default="")
    age = models.PositiveIntegerField()
    phone = models.CharField(max_length=32)
    customer_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "diagnostics_orders_order_customer"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "customer_profile"],
                name="uniq_diagnostics_order_customer",
            )
        ]

    def __str__(self):
        return f"{self.order_id}:{self.customer_profile_id}"


class DiagnosticOrderLine(BaseUUIDModel):
    order_customer = models.ForeignKey(
        DiagnosticOrderCustomer,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    test_id = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "diagnostics_orders_order_line"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order_customer", "test_id"],
                name="uniq_diagnostics_order_line_test",
            )
        ]

    def __str__(self):
        return f"{self.test_id}:{self.name}"


class DiagnosticOrderEvent(BaseUUIDModel):
    order = models.ForeignKey(
        DiagnosticOrder,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    orange_event_id = models.CharField(
        max_length=128, unique=True, null=True, blank=True
    )

    class Meta:
        db_table = "diagnostics_orders_order_event"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_id}:{self.event_type}"


class DiagnosticOrderRescheduleHistory(BaseUUIDModel):
    order = models.ForeignKey(
        DiagnosticOrder,
        on_delete=models.CASCADE,
        related_name="reschedule_history",
    )
    previous_slot_datetime = models.DateTimeField()
    new_slot_datetime = models.DateTimeField()
    reason = models.CharField(max_length=255)
    explanation = models.TextField(blank=True, default="")
    rescheduled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagnostic_order_reschedules",
    )

    class Meta:
        db_table = "diagnostics_orders_order_reschedule_history"
        ordering = ["-created_at"]
        verbose_name_plural = "Diagnostic Order Reschedule Histories"

    def __str__(self):
        return f"{self.order_id}:{self.previous_slot_datetime}:{self.new_slot_datetime}"


class DiagnosticsOrdersSummary(models.Model):
    id = models.SmallIntegerField(primary_key=True, default=1, editable=False)
    total_orders = models.PositiveIntegerField(default=0)
    total_rescheduled = models.PositiveIntegerField(default=0)
    total_cancelled = models.PositiveIntegerField(default=0)
    total_completed = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "diagnostics_orders_summary"

    def __str__(self):
        return f"summary:{self.id}"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)
