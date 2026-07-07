"""TextChoices and enums for pre-consultation session state and layer IDs."""

from django.db import models


class PreConsultationSessionInterface(models.TextChoices):
    MOBILE = "mobile", "Mobile"
    WEB = "web", "Web"


class PreConsultationSessionStatus(models.TextChoices):
    IN_PROGRESS = "inprogress", "In Progress"
    COMPLETED = "completed", "Completed"


class PreConsultationLayerProgression(models.TextChoices):
    """Ordered health-map layers; enum order matches client progression."""

    PATIENT_BASELINE = "patient_baseline", "Patient Baseline"
    PATIENT_CATEGORY = "patient_category", "Patient Category"
    PATIENT_CONCERN = "patient_concern", "Patient Concern"
    PATIENT_SYMPTOM = "patient_symptom", "Patient Symptom"
    PATIENT_CONCERN_PROBE = "patient_concern_probe", "Patient Concern Probe"
    PATIENT_CLUSTER_PROBE = "patient_cluster_probe", "Patient Cluster Probe"
    PATIENT_MEDICAL_HISTORY_CONTEXT = (
        "patient_medical_history_context",
        "Patient Medical History Context",
    )
    PATIENT_LIFESTYLE_ENVIRONMENT = (
        "patient_lifestyle_environment",
        "Patient Lifestyle Environment",
    )
    PATIENT_GOALS_PRIORITIES = "patient_goals_priorities", "Patient Goals Priorities"
    PATIENT_HEALTH_MAP = "patient_health_map", "Patient Health Map"


class PatientBaselineGender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"


class PreConsultationConcernSourceId(models.TextChoices):
    SYMPTOMS = "symptoms", "Symptoms"
    LAB_RESULT = "lab_result", "Lab Result"
    FAMILY = "family", "Family"
    CURIOSITY = "curiosity", "Curiosity"


class PreConsultationMedicationStatus(models.TextChoices):
    NO = "no", "No"
    MEDICATION = "medication", "Medication"
    SUPPLEMENTS = "supplements", "Supplements"
    MEDICATION_SUPPLEMENT = "medication_supplement", "Medication Supplement"


class PreConsultationArtifactGenerationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class PreConsultationSessionNoteCategory(models.TextChoices):
    GENERAL = "general", "General"
    INVESTIGATION = "investigation", "Investigation"
    TREATMENT = "treatment", "Treatment"
    FOLLOW_UP = "follow_up", "Follow-up"
    QUESTION = "question", "Question"
