from django.db import models


class NotificationProjectID(models.TextChoices):
    APP = "health-app-36fd7", "Biopeak App"
    ADMIN = "biopeak-admin", "Biopeak Admin"


class NotificationType(models.TextChoices):
    CUSTOM = "custom", "Custom Event"
    METSIGHTS_FILE_UPLOAD = "metsights.files.upload", "MetSights File Upload Event"
    METSIGHTS_PLAN_UPLOAD = "metsights.plan.upload", "MetSights Plan Upload Event"
