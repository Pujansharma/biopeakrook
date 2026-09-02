from django.db import models
from django.db.models.functions import Lower

from core.utils.constants import AppointmentModes
from core.utils.models import BaseUUIDModel
from products.models import Product
from programs.services.utils.constants import (
    ServiceCategory,
    ServiceDocumentCategory,
    ServiceDocumentType,
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
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="uniq_service_name",
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CenterServiceAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="service_assignments"
    )
    duration = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Appointment duration in minutes for this center",
    )
    buffer_before = models.PositiveSmallIntegerField(
        default=0, help_text="Buffer minutes before the appointment"
    )
    buffer_after = models.PositiveSmallIntegerField(
        default=0, help_text="Buffer minutes after the appointment"
    )
    modality = models.CharField(choices=AppointmentModes, default=AppointmentModes.BOTH)
    required_room_type = models.ForeignKey(
        "inventory.RoomType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_assignments",
    )
    required_equipment_type = models.ForeignKey(
        "inventory.EquipmentType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_assignments",
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


class CenterServiceRoleRequirement(BaseUUIDModel):
    assignment = models.ForeignKey(
        CenterServiceAssignment,
        on_delete=models.CASCADE,
        related_name="role_requirements",
    )
    role = models.ForeignKey(
        "associates.AssociateRole",
        on_delete=models.PROTECT,
        related_name="service_role_requirements",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "role"], name="uniq_assignment_role_requirement"
            )
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


class ServiceResult(BaseUUIDModel):
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

    class Meta:
        ordering = ["-created_at"]

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
