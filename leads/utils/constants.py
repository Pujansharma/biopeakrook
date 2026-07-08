from django.db import models


class LeadPackages(models.TextChoices):
    ESSENTIAL_HEALTH = "P001", "Essential Health Program"
    ESSENTIAL_HEALTH_DIGITAL_TWIN = "P002", "Essential Health with Digital Twin"
    EDGE = "P003", "Edge Program"
    EDGE_PLUS = "P004", "Edge Plus Program"
    ELITE_LONGEVITY = "P005", "Elite Longevity Programme"
    CUSTOMISED = "P006", "Customised Program"
