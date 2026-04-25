from django.contrib.postgres.fields import ArrayField
from django.db import models

from appointments.utils.constants import ScheduleModes
from core.utils.models import BaseUUIDModel
from inventory.utils.constants import DeviceType, RoomType
from services.utils.constants import ServiceCategory


class Service(BaseUUIDModel):
    """Specific service offerings"""
    center = models.ForeignKey(
        'centers.Center', related_name='services', on_delete=models.PROTECT
    )
    category = models.CharField(choices=ServiceCategory)
    name = models.CharField(max_length=200)
    pricing = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration = models.PositiveIntegerField(default=0)  # minutes
    requires_device = models.BooleanField(default=False)
    requires_room = models.BooleanField(default=True)
    mode_supported = models.CharField(choices=ScheduleModes)

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
