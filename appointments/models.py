from django.db import models

from accounts.associates.models import Associate
from accounts.centers.models import Center
from accounts.utils import get_user_model
from appointments.utils.constants import LeaveScope
from core.utils.constants import AppointmentDays
from core.utils.models import BaseUUIDModel
from inventory.models import Equipment, Room

User = get_user_model()


class AssociateRosterEntry(BaseUUIDModel):
    """Weekly recurring associate work hours at a center."""

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="associate_roster_entries"
    )
    associate = models.ForeignKey(
        Associate, on_delete=models.CASCADE, related_name="roster_entries"
    )
    day_of_week = models.CharField(choices=AppointmentDays)
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_associate_roster_entries",
    )

    class Meta:
        ordering = ["-created_at", "day_of_week"]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "associate", "day_of_week", "start_time", "end_time"],
                name="uniq_associate_roster_slot",
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class AssociateAvailabilityBlock(BaseUUIDModel):
    """One-off or weekly recurring associate unavailability at a center."""

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="associate_availability_blocks"
    )
    associate = models.ForeignKey(
        Associate, on_delete=models.CASCADE, related_name="availability_blocks"
    )
    is_recurring = models.BooleanField(default=False)
    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)
    day_of_week = models.CharField(choices=AppointmentDays, null=True, blank=True)
    recurring_start_time = models.TimeField(null=True, blank=True)
    recurring_end_time = models.TimeField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_associate_availability_blocks",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class AssociateLeave(BaseUUIDModel):
    """Associate leave — center-scoped or across all centers."""

    associate = models.ForeignKey(
        Associate, on_delete=models.CASCADE, related_name="leaves"
    )
    scope = models.CharField(
        choices=LeaveScope, default=LeaveScope.CENTER
    )
    center = models.ForeignKey(
        Center,
        on_delete=models.CASCADE,
        related_name="associate_leaves",
        null=True,
        blank=True,
    )
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_associate_leaves",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class RoomAvailabilityBlock(BaseUUIDModel):
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="availability_blocks"
    )
    is_recurring = models.BooleanField(default=False)
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day_of_week = models.CharField(choices=AppointmentDays, null=True, blank=True)
    recurring_start_time = models.TimeField(null=True, blank=True)
    recurring_end_time = models.TimeField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_room_availability_blocks",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class RoomDowntime(BaseUUIDModel):
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="downtimes"
    )
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_room_downtimes",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class EquipmentAvailabilityBlock(BaseUUIDModel):
    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name="availability_blocks"
    )
    is_recurring = models.BooleanField(default=False)
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day_of_week = models.CharField(choices=AppointmentDays, null=True, blank=True)
    recurring_start_time = models.TimeField(null=True, blank=True)
    recurring_end_time = models.TimeField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_equipment_availability_blocks",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class EquipmentDowntime(BaseUUIDModel):
    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name="downtimes"
    )
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_equipment_downtimes",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
