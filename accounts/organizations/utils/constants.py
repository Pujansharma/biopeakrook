from django.db import models


class FeatureTabOptions(models.TextChoices):
    REPORTS = "reports", "Reports"
    ANALYSIS = "analysis", "Analysis"
    ACTION_PLAN = "action_plan", "Action Plan"
    CARE_TEAM = "care_team", "Care Team"
    PERSONALISED_PLAN = "personalised_plan", "Personalised Guidebook"
    WELLNESS = "wellness", "Wellness"
    WEARABLES = "wearables", "Wearables"
