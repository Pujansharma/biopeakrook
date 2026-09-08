from django.db import models

from core.utils.models import BaseUUIDModel
from products.models import Product
from programs.services.utils.constants import (
    ServiceCategory,
    ServiceDocumentCategory,
    ServiceDocumentType,
    ResultRequestStatus,
    ServiceResultMode,
)


class Service(BaseUUIDModel):
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_services",
    )
    service_category = models.CharField(choices=ServiceCategory)
    image = models.FileField(upload_to="products/services/", null=True, blank=True)
    is_global = models.BooleanField(default=False)
    centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    products_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class CenterServiceAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="service_assignments"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "center"], name="unique_service_center"
            )
        ]
        indexes = [
            models.Index(fields=["service", "center"], name="service_center_idx")
        ]

    def __str__(self):
        return f"{self.pk}"


class ServiceProductAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="product_assignments"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="service_assignments"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "product"], name="unique_service_product"
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class ResultRequest(BaseUUIDModel):
    program_service = models.ForeignKey(
        "programs.ProgramService",
        on_delete=models.PROTECT,
        related_name="result_requests",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="result_requests",
    )
    data = models.JSONField(default=dict, blank=True)
    profile_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        choices=ResultRequestStatus,
        default=ResultRequestStatus.QUEUED,
        editable=False,
        db_index=True,
    )
    attempts_count = models.PositiveIntegerField(default=0, editable=False)
    failure_detail = models.TextField(default="", blank=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_result_requests",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ServiceResult(BaseUUIDModel):
    result_request = models.ForeignKey(
        ResultRequest,
        on_delete=models.PROTECT,
        related_name="results",
        null=True,
        blank=True,
        editable=False,
    )
    program_service = models.ForeignKey(
        "programs.ProgramService",
        on_delete=models.PROTECT,
        related_name="results",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="service_results",
        null=True,
        blank=True,
    )
    provider_name = models.CharField(
        max_length=200, null=True, blank=True, editable=False
    )
    product_name = models.CharField(
        max_length=100, null=True, blank=True, editable=False
    )

    result_mode = models.CharField(
        choices=ServiceResultMode, default=ServiceResultMode.UPLOAD, editable=False
    )

    document_type = models.CharField(
        choices=ServiceDocumentType, default=ServiceDocumentType.OTHER
    )
    documents_count = models.PositiveBigIntegerField(default=0, editable=False)
    sample_collection_date = models.DateField(null=True, blank=True)
    report_generation_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_service_results",
    )
    data = models.JSONField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["result_request", "document_type"],
                condition=models.Q(result_request__isnull=False),
                name="unique_result_request_document_type",
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class ServiceDocument(BaseUUIDModel):
    result = models.ForeignKey(
        ServiceResult, on_delete=models.CASCADE, related_name="documents"
    )

    file = models.FileField(upload_to="services/documents/")
    filename = models.CharField(max_length=255, editable=False)
    content_type = models.CharField(max_length=127, editable=False)
    file_hash = models.TextField(editable=False)

    document_category = models.CharField(choices=ServiceDocumentCategory)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
