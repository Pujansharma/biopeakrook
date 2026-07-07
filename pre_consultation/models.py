"""ORM models for the pre-consultation health-map session.

One PreConsultationSession per user tracks layer progression and client metadata.
Layer answers persist as normalized rows (concerns, medical history, lifestyle, etc.).
Cluster scores are computed on write and stored in PreConsultationSessionClusterScore.
Post-completion AI outputs persist in PreConsultationSessionArtifacts,
PreConsultationPreparationChecklistItem, and PreConsultationMedicalReportSummary.
"""

from django.db import models

from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from pre_consultation.utils.medical_report import medical_report_upload_to
from pre_consultation.utils.constants import (
    PreConsultationArtifactGenerationStatus,
    PreConsultationLayerProgression,
    PreConsultationMedicationStatus,
    PreConsultationSessionInterface,
    PreConsultationSessionNoteCategory,
    PreConsultationSessionStatus,
)

User = get_user_model()


# --- Session root -----------------------------------------------------------

class PreConsultationSession(BaseUUIDModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="pre_consultation_session",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    directive_schema_id = models.CharField(max_length=50, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=PreConsultationSessionStatus.choices,
        default=PreConsultationSessionStatus.IN_PROGRESS,
        db_index=True,
    )
    current_layer = models.CharField(
        max_length=50,
        choices=PreConsultationLayerProgression.choices,
        default=PreConsultationLayerProgression.PATIENT_BASELINE,
    )
    interface = models.CharField(
        max_length=10,
        choices=PreConsultationSessionInterface.choices,
    )
    app_version = models.CharField(max_length=50)
    locale = models.CharField(max_length=20)
    device = models.CharField(max_length=255)

    class Meta:
        db_table = "pre_consultation_session"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


# --- Category & concern tree (layers 2–6) -----------------------------------

class PreConsultationCategorySelection(BaseUUIDModel):
    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="category_selections",
    )
    category_id = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_category_selection"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "category_id"],
                name="pre_consultation_category_selection_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationConcern(BaseUUIDModel):
    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="concerns",
    )
    concern_id = models.CharField(max_length=100)
    functional_impact_id = models.CharField(max_length=100, blank=True, default="")
    duration_impact_id = models.CharField(max_length=100, blank=True, default="")
    progression_impact_id = models.CharField(max_length=100, blank=True, default="")
    # Set at concern_probe layer; used by cluster scoring and cluster_probe eligibility.
    probe_flagged = models.BooleanField(default=False)
    confidence_score = models.IntegerField(default=0)
    probe_question_count = models.IntegerField(default=0)
    probe_positive_count = models.IntegerField(default=0)

    class Meta:
        db_table = "pre_consultation_concern"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "concern_id"],
                name="pre_consultation_concern_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["session", "probe_flagged"],
                name="pc_concern_probe_flag_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationConcernSymptom(BaseUUIDModel):
    concern = models.ForeignKey(
        PreConsultationConcern,
        on_delete=models.CASCADE,
        related_name="symptoms",
    )
    symptom_id = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_concern_symptom"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["concern", "symptom_id"],
                name="pre_consultation_concern_symptom_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationConcernSource(BaseUUIDModel):
    concern = models.ForeignKey(
        PreConsultationConcern,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    source_id = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_concern_source"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["concern", "source_id"],
                name="pre_consultation_concern_source_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationConcernFamilyHistory(BaseUUIDModel):
    concern = models.ForeignKey(
        PreConsultationConcern,
        on_delete=models.CASCADE,
        related_name="family_history",
    )
    relation_id = models.CharField(max_length=100)
    age_band_id = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_concern_family_history"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["concern", "relation_id"],
                name="pre_consultation_concern_family_history_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationConcernProbeAnswer(BaseUUIDModel):
    concern = models.ForeignKey(
        PreConsultationConcern,
        on_delete=models.CASCADE,
        related_name="probe_answers",
    )
    probe_id = models.CharField(max_length=100)
    value = models.SmallIntegerField()

    class Meta:
        db_table = "pre_consultation_concern_probe_answer"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["concern", "probe_id"],
                name="pre_consultation_concern_probe_answer_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(value__in=[0, 1]),
                name="pre_consultation_concern_probe_answer_value",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


# --- Medical history (layer 7) ----------------------------------------------

class PreConsultationMedicalHistory(BaseUUIDModel):
    session = models.OneToOneField(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="medical_history",
    )
    medication_status = models.CharField(
        max_length=30,
        choices=PreConsultationMedicationStatus.choices,
        blank=True,
        default="",
    )

    class Meta:
        db_table = "pre_consultation_medical_history"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationDiagnosis(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )
    diagnosis_id = models.CharField(max_length=100)
    is_reproductive = models.BooleanField(default=False)

    class Meta:
        db_table = "pre_consultation_diagnosis"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["medical_history", "diagnosis_id"],
                name="pre_consultation_diagnosis_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationAllergy(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="allergies",
    )
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "pre_consultation_allergy"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationSurgery(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="surgeries",
    )
    name = models.CharField(max_length=255)
    performed_when = models.CharField(max_length=100)
    reason = models.CharField(max_length=255)

    class Meta:
        db_table = "pre_consultation_surgery"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationMedication(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="medications",
    )
    name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_medication"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationSexualHealthAnswer(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="sexual_health_answers",
    )
    question_id = models.CharField(max_length=100)
    option_id = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_sexual_health_answer"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["medical_history", "question_id"],
                name="pre_consultation_sexual_health_answer_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationMedicalReport(BaseUUIDModel):
    medical_history = models.ForeignKey(
        PreConsultationMedicalHistory,
        on_delete=models.CASCADE,
        related_name="medical_reports",
    )
    file = models.FileField(upload_to=medical_report_upload_to)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=127)
    file_size = models.PositiveIntegerField()

    class Meta:
        db_table = "pre_consultation_medical_report"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


# --- Lifestyle, cluster scores, goals (layers 8–10) -------------------------

class PreConsultationLifestyleAnswer(BaseUUIDModel):
    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="lifestyle_answers",
    )
    field_id = models.CharField(max_length=100)
    option_value = models.CharField(max_length=100)

    class Meta:
        db_table = "pre_consultation_lifestyle_answer"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "field_id"],
                name="pre_consultation_lifestyle_answer_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationSessionClusterScore(BaseUUIDModel):
    """Persisted output of lifestyle + cluster confidence engines per health cluster."""

    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="cluster_scores",
    )
    cluster_id = models.CharField(max_length=100)
    cluster_label = models.CharField(max_length=255)
    lifestyle_signal_count = models.PositiveSmallIntegerField(default=0)
    lifestyle_signals_triggered = models.JSONField(default=list)
    lifestyle_contribution = models.PositiveSmallIntegerField(default=0)
    base_concern_contribution = models.PositiveSmallIntegerField(default=0)
    family_risk_contribution = models.PositiveSmallIntegerField(default=0)
    provisional_score = models.PositiveSmallIntegerField(default=0)
    validation_probed = models.BooleanField(default=False)
    validation_contribution = models.PositiveSmallIntegerField(default=0)
    # Populated when cluster_probe skipped: settled | weak_signal | not_probed.
    validation_skip_reason = models.CharField(max_length=50, blank=True, default="")
    final_score = models.PositiveSmallIntegerField(default=0)
    bucket_id = models.CharField(max_length=100, blank=True, default="")
    bucket_label = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "pre_consultation_session_cluster_score"
        ordering = ["cluster_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "cluster_id"],
                name="pre_consultation_session_cluster_score_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationHealthGoal(BaseUUIDModel):
    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="health_goals",
    )
    goal_id = models.CharField(max_length=100)
    priority = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "pre_consultation_health_goal"
        ordering = ["priority"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "goal_id"],
                name="pre_consultation_health_goal_id_unique",
            ),
            models.UniqueConstraint(
                fields=["session", "priority"],
                name="pre_consultation_health_goal_priority_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}"


# --- Post-completion AI artifacts (generated after session/complete) --------

class PreConsultationSessionArtifacts(BaseUUIDModel):
    """Session-level generated summaries; one row per completed session."""

    session = models.OneToOneField(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    summary = models.TextField(blank=True, default="")
    quick_summary = models.TextField(blank=True, default="")
    family_risk_summary = models.TextField(blank=True, default="")
    generation_status = models.CharField(
        max_length=20,
        choices=PreConsultationArtifactGenerationStatus.choices,
        default=PreConsultationArtifactGenerationStatus.PENDING,
        db_index=True,
    )
    generation_started_at = models.DateTimeField(null=True, blank=True)
    generation_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pre_consultation_session_artifacts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationPreparationChecklistItem(BaseUUIDModel):
    """Consultation prep checklist item; identified_concern is generated, marked is user-toggleable."""

    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="preparation_checklist_items",
    )
    identified_concern = models.TextField()
    marked = models.BooleanField(default=False)

    class Meta:
        db_table = "pre_consultation_preparation_checklist_item"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationMedicalReportSummary(BaseUUIDModel):
    """Generated summary for one uploaded medical report."""

    medical_report = models.OneToOneField(
        PreConsultationMedicalReport,
        on_delete=models.CASCADE,
        related_name="summary",
    )
    summary = models.TextField(blank=True, default="")
    testing_location = models.CharField(max_length=255, blank=True, default="")
    testing_date = models.DateField(null=True, blank=True)
    is_flagged = models.BooleanField(default=False)
    generation_status = models.CharField(
        max_length=20,
        choices=PreConsultationArtifactGenerationStatus.choices,
        default=PreConsultationArtifactGenerationStatus.PENDING,
        db_index=True,
    )

    class Meta:
        db_table = "pre_consultation_medical_report_summary"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class PreConsultationSessionNote(BaseUUIDModel):
    """Associate-authored note linked to a completed pre-consultation session."""

    session = models.ForeignKey(
        PreConsultationSession,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    note = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=PreConsultationSessionNoteCategory.choices,
        db_index=True,
    )

    class Meta:
        db_table = "pre_consultation_session_note"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"
