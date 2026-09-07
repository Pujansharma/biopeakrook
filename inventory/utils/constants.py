from django.db import models


class LegacyRoomType:
    """Legacy CharField choices on Room.room_type (Phase A). Prefer RoomType model."""

    CONSULTATION = "consultation"
    THERAPY = "therapy"
    BLOOD_COLLECTION = "blood_collection"
    IMAGING = "imaging"
    LAB = "lab"
    WAITING = "waiting"

    CHOICES = (
        (CONSULTATION, "Consultation Room"),
        (THERAPY, "Therapy Room"),
        (BLOOD_COLLECTION, "Blood Collection Room"),
        (IMAGING, "Imaging Room"),
        (LAB, "Laboratory"),
        (WAITING, "Waiting Area"),
    )


# Backwards-compatible alias for existing imports.
RoomType = LegacyRoomType


class LegacyDeviceType:
    """Legacy CharField choices on Equipment.device_type (Phase A). Prefer EquipmentType model."""

    SAMPLING_DEVICE = "sampling_device"
    DEXA_MACHINE = "dexa_machine"
    ULTRASOUND = "ultrasound"
    LAB_ANALYZER = "lab_analyzer"
    THERAPY_EQUIPMENT = "therapy_equipment"

    CHOICES = (
        (SAMPLING_DEVICE, "Blood Sampling Device"),
        (DEXA_MACHINE, "DEXA Machine"),
        (ULTRASOUND, "Ultrasound Machine"),
        (LAB_ANALYZER, "Lab Analyzer"),
        (THERAPY_EQUIPMENT, "Therapy Equipment"),
    )


DeviceType = LegacyDeviceType


class EquipmentPortability(models.TextChoices):
    FIXED = "fixed", "Fixed"
    PORTABLE = "portable", "Portable"


class EquipmentOperationalStatus(models.TextChoices):
    OPERATIONAL = "operational", "Operational"
    MAINTENANCE = "maintenance", "In Maintenance"
    DOWNTIME = "downtime", "Downtime"
