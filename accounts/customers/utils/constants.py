from django.db import models


class AddressType(models.TextChoices):
    HOME = "home", "Home"
    OFFICE = "office", "Office"
    OTHER = "other", "Other"
