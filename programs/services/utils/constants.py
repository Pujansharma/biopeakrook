from django.db import models


class ServiceCategory(models.TextChoices):
    THERAPY = "therapy", "Therapy"
    CONSULTATION = "consultation", "Consultation"
    ASSESSMENT = "assessment", "Assessment"
