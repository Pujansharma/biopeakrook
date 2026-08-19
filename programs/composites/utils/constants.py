from django.db import models


class PrerequisiteCondition(models.TextChoices):
    REQUIRE_ALL = "require_all", "All Required"
    REQUIRE_ANY = "require_any", "Any one required"


class CompositeAssessmentType(models.TextChoices):
    BASELINE = "baseline", "Baseline"
    ANNUAL = "annual", "Annual"
    SIX_MONTH_REVIEW = "six_month_review", "6 Months Review"
    RETEST = "retest", "Retest"
    SPECIAL_INVESTIGATION = "special_investigation", "Special Investigation"
