from django.db import models
from django.utils import timezone

from core.utils.models import BaseModel, BaseUUIDModel
from programs.composites.utils.constants import CompositeAssessmentType
from programs.utils.constants import ProgramType, RedemptionType, ServiceAssignment
from programs.utils.helper import generate_redeemable_code


class Program(BaseUUIDModel):
    uid = models.CharField(null=True, blank=True, editable=False)
    customer_profile = models.ForeignKey(
        "customers.CustomerProfile", related_name="programs", on_delete=models.PROTECT
    )
    center = models.ForeignKey(
        "centers.Center", related_name="programs", on_delete=models.PROTECT
    )
    program_type = models.CharField(choices=ProgramType)
    notes = models.TextField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    is_complimentary = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    redeemable_centers = models.ManyToManyField(
        "centers.Center", related_name="redeemable_programs", blank=True
    )
    services_count = models.PositiveBigIntegerField(default=0, editable=False)
    services_cancelled = models.PositiveBigIntegerField(default=0, editable=False)

    redeemable_centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_programs",
    )

    cancellation_reason = models.TextField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_programs",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_date = models.DateField(default=timezone.localdate)
    cancelled_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ProgramService(BaseUUIDModel):
    data = models.JSONField(default=dict, blank=True, editable=False)

    program = models.ForeignKey(
        Program, related_name="program_services", on_delete=models.CASCADE
    )
    service = models.ForeignKey(
        "services.Service", related_name="program_services", on_delete=models.PROTECT
    )
    assignment_type = models.CharField(
        choices=ServiceAssignment, default=ServiceAssignment.STANDALONE
    )
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_program_services",
        editable=False,
    )
    cancellation_reason = models.TextField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_program_services",
        editable=False,
    )
    cancelled_at = models.DateTimeField(editable=False, null=True, blank=True)

    created_date = models.DateField(default=timezone.localdate)
    cancelled_date = models.DateField(null=True, blank=True)
    results_count = models.PositiveBigIntegerField(default=0, editable=False)
    documents_count = models.PositiveBigIntegerField(default=0, editable=False)
    reports_count = models.PositiveBigIntegerField(default=0, editable=False)
    raw_data_count = models.PositiveBigIntegerField(default=0, editable=False)

    fetch_count = models.PositiveBigIntegerField(default=0, editable=False)
    fetch_results_count = models.PositiveBigIntegerField(default=0, editable=False)
    fetch_documents_count = models.PositiveBigIntegerField(default=0, editable=False)
    fetch_pending_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class TherapyProgram(BaseModel):
    program = models.OneToOneField(
        Program,
        on_delete=models.CASCADE,
        related_name="therapy_program",
        primary_key=True,
        db_index=True,
    )
    sessions_count = models.PositiveBigIntegerField(default=0, editable=False)
    sessions_used = models.PositiveBigIntegerField(default=0, editable=False)
    sessions_cancelled = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class TherapyProgramService(BaseModel):
    program_service = models.OneToOneField(
        ProgramService,
        related_name="therapy_service",
        on_delete=models.CASCADE,
        primary_key=True,
        db_index=True,
    )
    sessions_count = models.PositiveIntegerField(default=0)
    sessions_used = models.PositiveIntegerField(default=0, editable=False)
    sessions_cancelled = models.PositiveBigIntegerField(default=0, editable=False)
    redeem_code = models.CharField(
        max_length=10, default=generate_redeemable_code, editable=False
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["redeem_code", "program_service"], name="therapy_redeem_idx"
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class AssessmentProgram(BaseModel):
    program = models.OneToOneField(
        Program,
        on_delete=models.CASCADE,
        related_name="assessment_program",
        primary_key=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class AssessmentProgramService(BaseModel):
    program_service = models.OneToOneField(
        ProgramService,
        related_name="assessment_service",
        on_delete=models.CASCADE,
        primary_key=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ConsultationProgram(BaseModel):
    program = models.OneToOneField(
        Program,
        on_delete=models.CASCADE,
        related_name="consultation_program",
        primary_key=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ConsultationProgramService(BaseModel):
    program_service = models.OneToOneField(
        ProgramService,
        related_name="consultation_service",
        on_delete=models.CASCADE,
        primary_key=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class RedemptionHistory(BaseUUIDModel):
    therapy_program_service = models.ForeignKey(
        TherapyProgramService, on_delete=models.PROTECT, related_name="redemptions"
    )
    redeem_center = models.ForeignKey(
        "centers.Center", on_delete=models.PROTECT, related_name="redemptions"
    )
    appointment = models.OneToOneField(
        "appointments.Appointment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="redemption_history",
    )
    redeemed_at = models.DateTimeField(editable=False)
    redeemed_date = models.DateField(default=timezone.localdate)
    quantity = models.PositiveIntegerField(default=0)
    redeemed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="redeemed_histories",
    )
    notes = models.TextField(blank=True)
    redemption_type = models.CharField(
        choices=RedemptionType, default=RedemptionType.REDEEM, editable=False
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Redemption Histories"
        indexes = [
            models.Index(
                fields=["therapy_program_service", "redemption_type"],
                name="redemption_tps_type_idx",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CompositeProgram(BaseModel):
    program = models.OneToOneField(
        Program,
        on_delete=models.CASCADE,
        related_name="composite_program",
        primary_key=True,
        db_index=True,
    )
    composite_template = models.ForeignKey(
        "composites.CompositeTemplate",
        related_name="assigned_programs",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=200, null=True, blank=True)
    assessment_type = models.CharField(
        choices=CompositeAssessmentType,
        null=True,
        blank=True,
    )
    template_description = models.TextField(null=True, blank=True, editable=False)
    add_ons_count = models.PositiveBigIntegerField(default=0, editable=False)
    assessment_services_count = models.PositiveBigIntegerField(default=0, editable=False)
    therapy_services_count = models.PositiveBigIntegerField(default=0, editable=False)
    consultation_services_count = models.PositiveBigIntegerField(default=0, editable=False)

    results_count = models.PositiveBigIntegerField(default=0, editable=False)
    documents_count = models.PositiveBigIntegerField(default=0, editable=False)
    reports_count = models.PositiveBigIntegerField(default=0, editable=False)
    raw_data_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
