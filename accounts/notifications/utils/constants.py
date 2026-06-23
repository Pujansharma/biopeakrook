from django.db import models


class NotificationType(models.TextChoices):
    CUSTOM = "custom", "Custom Event"
    METSIGHTS_FILE_UPLOAD = "metsights.files.upload", "MetSights File Upload Event"
