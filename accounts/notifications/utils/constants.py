from django.db import models


class NotificationProjectID:
    APP = "health-app-36fd7"
    ADMIN = "biopeak-admin"


class NotificationType(models.TextChoices):
    CUSTOM = "custom", "Custom Event"
    METSIGHTS_FILE_UPLOAD = "metsights.files.upload", "MetSights File Upload Event"
