from django.db import models


class ProgramType(models.TextChoices):
    WELLNESS = "wellness", "Wellness"
