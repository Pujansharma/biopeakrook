from django.db import models

from accounts.utils import get_user_model
from appointments.utils.constants import AppointmentDays
from core.utils.models import BaseUUIDModel
from inventory.utils.constants import RoomType, DeviceType

User = get_user_model()


class Room(BaseUUIDModel):
    """Physical rooms at centers"""
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='rooms'
    )
    room_type = models.CharField(choices=RoomType.CHOICES)
    name = models.CharField(max_length=100)  # "Consultation Room 1"
    code = models.CharField(max_length=50, unique=True)  # "BLR-S-CR-01"

    capacity = models.PositiveIntegerField(default=1)  # For group sessions
    floor = models.CharField(max_length=20, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_rooms'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class RoomSchedule(BaseUUIDModel):
    """Room availability windows"""
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name='schedules'
    )

    day_of_week = models.CharField(choices=AppointmentDays.CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    schedule_type = models.CharField(choices=[
        ('operational', 'Operational'),
        ('maintenance', 'Maintenance'),
        ('reserved', 'Reserved')
    ])
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_room_schedules'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class Equipment(BaseUUIDModel):
    """Actual device instances"""
    device_type = models.CharField(choices=DeviceType.CHOICES)
    code = models.CharField(max_length=20, unique=True)

    center = models.ForeignKey(
        'centers.Center', related_name='equipments', on_delete=models.PROTECT
    )

    room = models.ForeignKey(
        Room, related_name='equipments', on_delete=models.PROTECT, null=True, blank=True
    )

    serial_number = models.CharField(max_length=100)
    name = models.CharField(max_length=100)  # "DEXA-001"

    # Operational parameters
    setup_time = models.PositiveIntegerField(default=0)  # minutes
    cooldown_time = models.PositiveIntegerField(default=0)
    requires_technician = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_equipments'
    )

    class Meta:
        ordering = ['-created_at']


class EquipmentSchedule(BaseUUIDModel):
    """Device availability and maintenance windows"""
    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name='schedules'
    )

    # Similar to Associate Schedule
    day_of_week = models.CharField(choices=AppointmentDays.CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    # Purpose: operational vs maintenance
    schedule_type = models.CharField(choices=[
        ('operational', 'Operational'),
        ('maintenance', 'Maintenance'),
        ('reserved', 'Reserved')
    ])

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_equipment_schedules'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class EquipmentBooking(BaseUUIDModel):
    """Track device usage"""
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name='bookings')
    appointment = models.ForeignKey(
        'appointments.Appointment', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='devices'
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    booked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='device_bookings'
    )
    purpose = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_equipment_bookings'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class EquipmentMaintenance(BaseUUIDModel):
    """One-off or scheduled maintenance records"""
    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name='maintenance_records'
    )

    maintenance_type = models.CharField(
        max_length=50,
        choices=[
            ('routine', 'Routine Maintenance'),
            ('repair', 'Repair'),
            ('calibration', 'Calibration'),
            ('inspection', 'Inspection'),
            ('emergency', 'Emergency Repair')
        ]
    )

    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()

    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled')
        ],
        default='scheduled'
    )

    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='performed_maintenances'
    )
    notes = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_equipment_maintenances'
    )

    class Meta:
        ordering = ['-scheduled_start']
        verbose_name_plural = "Equipment Maintenance Records"

    def __str__(self):
        return f"{self.pk}"
