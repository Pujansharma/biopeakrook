from django.contrib.postgres.fields import ArrayField
from django.db import models

from appointments.utils.constants import ScheduleModes
from core.utils.models import BaseUUIDModel
from inventory.utils.constants import DeviceType, RoomType
from services.utils.constants import ServiceCategory


# Examples: "Endocrinology Consultation", "DEXA Scan", "Physiotherapy Session"
class Service(BaseUUIDModel):
    """Specific service offerings"""
    category = models.CharField(choices=ServiceCategory.CHOICES)
    name = models.CharField(max_length=200)

    duration = models.PositiveIntegerField()  # minutes
    requires_device = models.BooleanField(default=False)
    requires_room = models.BooleanField(default=True)
    mode_supported = models.CharField(choices=ScheduleModes.CHOICES)

    device_types = ArrayField(
        base_field=models.CharField(choices=DeviceType.CHOICES), max_length=len(DeviceType.CHOICES)
    )
    room_types = ArrayField(
        base_field=models.CharField(choices=RoomType.CHOICES), max_length=len(RoomType.CHOICES)
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class ServiceAvailability(BaseUUIDModel):
    """Which services are offered at which centers"""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='availability')
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='availability'
    )
    pricing = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"
