from django.db import models

from core.utils.models import BaseModel, BaseUUIDModel
from programs.composites.utils.constants import PrerequisiteCondition


class CompositeTemplate(BaseUUIDModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    services_count = models.PositiveBigIntegerField(default=0, editable=False)
    assessment_services_count = models.PositiveBigIntegerField(default=0, editable=False)
    therapy_services_count = models.PositiveBigIntegerField(default=0, editable=False)
    consultation_services_count = models.PositiveBigIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_composite_templates",
        editable=False,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class CompositeTemplateService(BaseUUIDModel):
    composite_template = models.ForeignKey(
        CompositeTemplate, related_name="services", on_delete=models.CASCADE
    )
    service = models.ForeignKey(
        "services.Service", related_name="template_services", on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_composite_template_services",
        editable=False,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["composite_template", "service"],
                name="unique_composite_template_service",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CompositeServicePrerequisite(BaseModel):
    template_service = models.OneToOneField(
        CompositeTemplateService,
        on_delete=models.CASCADE,
        related_name="prerequisite",
    )
    related_services = models.ManyToManyField(
        CompositeTemplateService,
        related_name="related_prerequisites",
        blank=True,
    )
    related_services_count = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    condition = models.CharField(
        choices=PrerequisiteCondition, default=PrerequisiteCondition.REQUIRE_ANY
    )
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_composite_service_prerequisites",
        editable=False,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"
