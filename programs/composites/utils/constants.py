from django.db import models


class PrerequisiteCondition(models.TextChoices):
    REQUIRE_ALL = "require_all", "All Required"
    REQUIRE_ANY = "require_any", "Any one required"


class CompositeAssessmentType(models.TextChoices):
    BASELINE = "baseline", "Baseline"
