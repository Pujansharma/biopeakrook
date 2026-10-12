from django.db import models


class ProgramType(models.TextChoices):
    THERAPY = "therapy", "Therapy Program"
    ASSESSMENT = "assessment", "Assessment Program"
    CONSULTATION = "consultation", "Consultation"
    COMPOSITE = "composite", "Composite"


class RedemptionType(models.TextChoices):
    REDEEM = "redeem", "Redeem"
    CANCEL = "cancel", "Cancel"
    SCHEDULED = "scheduled", "Scheduled"
    CANCELLED = "cancelled", "Cancelled"


class ServiceAssignment(models.TextChoices):
    STANDALONE = "standalone", "Standalone"
    ADD_ON = "add_on", "Add On"
