from django.contrib.postgres.constraints import ExclusionConstraint
from django.db import models
from django.db.models import F, Func, Q
from django.db.models.functions import Lower

from accounts.associates.models import Associate, AssociateRole
from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.utils import get_user_model
from appointments.utils.constants import (
    AppointmentAuditAction,
    AppointmentStatus,
    AvailabilityOrigin,
    ExceptionResolution,
    ExceptionScanJobStatus,
    ExceptionSourceType,
    ExceptionStatus,
    LeaveScope,
)
from core.utils.constants import AppointmentDays, AppointmentModes
from core.utils.models import BaseUUIDModel
from inventory.models import Equipment, Room
from programs.services.models import Service

User = get_user_model()

# Stable order must match ExclusionConstraint migrations (not frozenset hash order).
_BUSY_STATUS_VALUES = ["confirmed", "checked_in", "in_progress"]


def _exclusive_range_expression():
    return Func(
        F("exclusive_start_datetime"),
        F("exclusive_end_datetime"),
        function="tstzrange",
        template="%(function)s(%(expressions)s, '[)')",
    )


def _care_team_one_off_range_expression():
    return Func(
        F("start_datetime"),
        F("end_datetime"),
        function="tstzrange",
        template="%(function)s(%(expressions)s, '[)')",
    )


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
    google_event_id = models.CharField(max_length=1024, blank=True, db_index=True)
    series_id = models.UUIDField(null=True, blank=True, db_index=True)
    origin = models.CharField(
        max_length=16,
        choices=AvailabilityOrigin,
        default=AvailabilityOrigin.MANUAL,
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_associate_availability_blocks",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Two concurrent Google syncs must not both import the same event
            models.UniqueConstraint(
                fields=["associate", "center", "google_event_id", "day_of_week"],
                condition=models.Q(is_active=True, origin=AvailabilityOrigin.GOOGLE)
                & ~models.Q(google_event_id=""),
                nulls_distinct=False,
                name="uniq_active_google_block_per_event",
            )
        ]

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
    google_event_id = models.CharField(max_length=1024, blank=True, db_index=True)
    origin = models.CharField(
        max_length=16,
        choices=AvailabilityOrigin,
        default=AvailabilityOrigin.MANUAL,
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_associate_leaves",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["associate", "google_event_id"],
                condition=models.Q(is_active=True, origin=AvailabilityOrigin.GOOGLE)
                & ~models.Q(google_event_id=""),
                name="uniq_active_google_leave_per_event",
            )
        ]

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


class CenterCareTeam(BaseUUIDModel):
    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="care_teams"
    )
    name = models.CharField(max_length=100)
    members_count = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_center_care_teams",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                "center",
                Lower("name"),
                name="uniq_center_care_team_name",
            ),
            models.CheckConstraint(
                condition=Q(members_count__gte=2),
                name="center_care_team_min_members",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CenterCareTeamMember(BaseUUIDModel):
    care_team = models.ForeignKey(
        CenterCareTeam,
        on_delete=models.CASCADE,
        related_name="members",
    )
    associate = models.ForeignKey(
        Associate,
        on_delete=models.CASCADE,
        related_name="care_team_memberships",
    )
    role = models.ForeignKey(
        AssociateRole,
        on_delete=models.PROTECT,
        related_name="care_team_memberships",
    )

    class Meta:
        ordering = ["role"]
        constraints = [
            models.UniqueConstraint(
                fields=["care_team", "role"],
                name="uniq_center_care_team_role",
            ),
            models.UniqueConstraint(
                fields=["care_team", "associate"],
                name="uniq_center_care_team_associate",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class CareTeamAvailabilityBlock(BaseUUIDModel):
    """One-off or weekly recurring unavailability for a care team at a center."""

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="care_team_availability_blocks"
    )
    care_team = models.ForeignKey(
        CenterCareTeam,
        on_delete=models.CASCADE,
        related_name="availability_blocks",
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
        related_name="created_care_team_availability_blocks",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["care_team", "is_active"]),
            models.Index(fields=["center", "care_team", "is_active"]),
        ]
        constraints = [
            ExclusionConstraint(
                name="care_team_block_one_off_no_overlap",
                expressions=[
                    (F("care_team_id"), "="),
                    (_care_team_one_off_range_expression(), "&&"),
                ],
                condition=Q(
                    is_active=True,
                    is_recurring=False,
                    start_datetime__isnull=False,
                    end_datetime__isnull=False,
                ),
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class Appointment(BaseUUIDModel):
    """
    Standalone center-scoped appointment booking.

    First migration must run: CREATE EXTENSION IF NOT EXISTS btree_gist;
    before GiST ExclusionConstraint definitions.
    """

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="appointments"
    )
    code = models.CharField(max_length=64)
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="appointments"
    )
    program_service = models.ForeignKey(
        "programs.ProgramService",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    modality = models.CharField(choices=AppointmentModes)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    buffer_before_minutes = models.PositiveIntegerField(default=0)
    buffer_after_minutes = models.PositiveIntegerField(default=0)
    exclusive_start_datetime = models.DateTimeField()
    exclusive_end_datetime = models.DateTimeField()
    status = models.CharField(
        choices=AppointmentStatus,
        default=AppointmentStatus.CONFIRMED,
    )
    is_late = models.BooleanField(default=False)
    late_by = models.PositiveIntegerField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True)
    has_open_exception = models.BooleanField(default=False)
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    care_team = models.ForeignKey(
        CenterCareTeam,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="booked_appointments",
    )
    notes = models.TextField(null=True, blank=True)
    google_event_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )
    google_meet_link = models.URLField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_appointments",
    )

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["center", "start_datetime"]),
            models.Index(fields=["center", "status", "start_datetime"]),
            models.Index(fields=["customer_profile", "start_datetime"]),
            models.Index(
                fields=["status", "start_datetime"],
                name="appointment_status_start_idx",
            ),
            models.Index(
                fields=["program_service", "status"],
                name="appt_ps_status_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "code"],
                name="uniq_appointment_code_per_center",
            ),
            models.UniqueConstraint(
                fields=["program_service"],
                condition=Q(
                    program_service__isnull=False,
                    status__in=_BUSY_STATUS_VALUES,
                ),
                name="uniq_open_appt_per_ps",
            ),
            models.CheckConstraint(
                condition=Q(end_datetime__gt=F("start_datetime")),
                name="appointment_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(
                    exclusive_end_datetime__gt=F("exclusive_start_datetime")
                ),
                name="appointment_exclusive_end_after_start",
            ),
            ExclusionConstraint(
                name="appointment_room_no_overlap",
                expressions=[
                    (F("room_id"), "="),
                    (_exclusive_range_expression(), "&&"),
                ],
                condition=Q(
                    room_id__isnull=False,
                    status__in=_BUSY_STATUS_VALUES,
                ),
            ),
            ExclusionConstraint(
                name="appointment_equipment_no_overlap",
                expressions=[
                    (F("equipment_id"), "="),
                    (_exclusive_range_expression(), "&&"),
                ],
                condition=Q(
                    equipment_id__isnull=False,
                    status__in=_BUSY_STATUS_VALUES,
                ),
            ),
            ExclusionConstraint(
                name="appointment_customer_no_overlap",
                expressions=[
                    (F("customer_profile_id"), "="),
                    (_exclusive_range_expression(), "&&"),
                ],
                condition=Q(status__in=_BUSY_STATUS_VALUES),
            ),
        ]

    def __str__(self):
        return self.code


class AppointmentAssociate(BaseUUIDModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="associate_links",
    )
    associate = models.ForeignKey(
        Associate,
        on_delete=models.CASCADE,
        related_name="appointment_links",
    )
    role = models.ForeignKey(
        AssociateRole,
        on_delete=models.PROTECT,
        related_name="appointment_links",
    )
    exclusive_start_datetime = models.DateTimeField()
    exclusive_end_datetime = models.DateTimeField()
    appointment_status = models.CharField(choices=AppointmentStatus)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["associate", "exclusive_start_datetime"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "role"],
                name="uniq_appointment_associate_role",
            ),
            models.UniqueConstraint(
                fields=["appointment", "associate"],
                name="uniq_appointment_associate",
            ),
            ExclusionConstraint(
                name="appointment_associate_no_overlap",
                expressions=[
                    (F("associate_id"), "="),
                    (_exclusive_range_expression(), "&&"),
                ],
                condition=Q(appointment_status__in=_BUSY_STATUS_VALUES),
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class AppointmentException(BaseUUIDModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="exceptions",
    )
    center = models.ForeignKey(
        Center,
        on_delete=models.CASCADE,
        related_name="appointment_exceptions",
    )
    source_type = models.CharField(choices=ExceptionSourceType)
    source_id = models.UUIDField()
    source_label = models.CharField(max_length=255, blank=True)
    source_start_datetime = models.DateTimeField()
    source_end_datetime = models.DateTimeField()
    status = models.CharField(
        choices=ExceptionStatus,
        default=ExceptionStatus.OPEN,
    )
    resolution = models.CharField(
        choices=ExceptionResolution,
        null=True,
        blank=True,
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["center", "status"]),
            models.Index(fields=["appointment", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "source_type", "source_id"],
                condition=Q(status=ExceptionStatus.OPEN),
                name="uniq_open_appointment_exception_source",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"


class AppointmentAuditLog(BaseUUIDModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_audit_logs",
    )
    action = models.CharField(choices=AppointmentAuditAction)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["appointment", "created_at"]),
        ]

    def __str__(self):
        return f"{self.pk}"


class AppointmentHistory(BaseUUIDModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    previous_start_datetime = models.DateTimeField()
    previous_end_datetime = models.DateTimeField()
    previous_exclusive_start_datetime = models.DateTimeField()
    previous_exclusive_end_datetime = models.DateTimeField()
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_history_entries",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class AppointmentExceptionScanJob(BaseUUIDModel):
    """Async queue for recurring/bulk exception overlap scans."""

    center = models.ForeignKey(
        Center,
        on_delete=models.CASCADE,
        related_name="appointment_exception_scan_jobs",
    )
    source_type = models.CharField(choices=ExceptionSourceType)
    source_id = models.UUIDField()
    status = models.CharField(
        choices=ExceptionScanJobStatus,
        default=ExceptionScanJobStatus.PENDING,
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["center", "status"]),
        ]

    def __str__(self):
        return f"{self.pk}"


class AppointmentIdempotencyKey(BaseUUIDModel):
    center = models.ForeignKey(
        Center,
        on_delete=models.CASCADE,
        related_name="appointment_idempotency_keys",
    )
    idempotency_key = models.CharField(max_length=255)
    payload_hash = models.CharField(max_length=64)
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["expires_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "idempotency_key"],
                name="uniq_appointment_idempotency_key_per_center",
            ),
        ]

    def __str__(self):
        return f"{self.pk}"
