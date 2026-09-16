import logging
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from accounts.associates.models import Associate
from accounts.centers.models import Center, CenterClosure
from appointments.models import (
    Appointment,
    AppointmentAuditLog,
    AppointmentException,
    AppointmentExceptionScanJob,
    AssociateAvailabilityBlock,
    AssociateLeave,
    CareTeamAvailabilityBlock,
    CenterCareTeamMember,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.utils.calendar import (
    expand_recurring_block,
    get_center_timezone_name,
)
from appointments.utils.care_teams import (
    members_with_live_center_role,
)
from appointments.utils.constants import (
    AppointmentAuditAction,
    BUSY_APPOINTMENT_STATUSES,
    ExceptionResolution,
    ExceptionScanJobStatus,
    ExceptionSourceType,
    ExceptionStatus,
    LeaveScope,
)
from appointments.utils.intervals import (
    datetime_range_for_dates,
    full_day_interval,
)
from appointments.utils.metrics import record_exceptions_detected
from appointments.utils.operations import invalidate_operations_cache
from appointments.utils.overlap import datetimes_overlap, local_day_window
from appointments.utils.scheduling import (
    compute_associate_free_windows,
    is_interval_contained_in_windows,
)

logger = logging.getLogger("appointments")

RECURRING_SCAN_HORIZON_DAYS = 90
SOURCE_MODEL_MAP = {
    ExceptionSourceType.ASSOCIATE_LEAVE: AssociateLeave,
    ExceptionSourceType.ASSOCIATE_BLOCK: AssociateAvailabilityBlock,
    ExceptionSourceType.CARE_TEAM_BLOCK: CareTeamAvailabilityBlock,
    ExceptionSourceType.ROOM_BLOCK: RoomAvailabilityBlock,
    ExceptionSourceType.EQUIPMENT_BLOCK: EquipmentAvailabilityBlock,
    ExceptionSourceType.ROOM_DOWNTIME: RoomDowntime,
    ExceptionSourceType.EQUIPMENT_DOWNTIME: EquipmentDowntime,
    ExceptionSourceType.CLOSURE: CenterClosure,
}


def recompute_appointment_exception_flag(appointment: Appointment) -> bool:
    has_open = AppointmentException.objects.filter(
        appointment=appointment,
        status=ExceptionStatus.OPEN,
    ).exists()
    appointment.has_open_exception = has_open
    appointment.save(update_fields=["has_open_exception", "updated_at"])
    return has_open


def resolve_exceptions_for_appointment(
    appointment: Appointment,
    resolution: str,
) -> int:
    now = timezone.now()
    updated = appointment.exceptions.filter(status=ExceptionStatus.OPEN).update(
        status=ExceptionStatus.RESOLVED,
        resolution=resolution,
        resolved_at=now,
        updated_at=now,
    )
    if updated:
        recompute_appointment_exception_flag(appointment)
    return updated


def resolve_exceptions_for_source(
    source_type: str,
    source_id,
    resolution: str = ExceptionResolution.BLOCKER_CLEARED,
) -> int:
    now = timezone.now()
    open_exceptions = AppointmentException.objects.filter(
        source_type=source_type,
        source_id=source_id,
        status=ExceptionStatus.OPEN,
    ).select_related("appointment")
    appointment_ids = list(
        open_exceptions.values_list("appointment_id", flat=True).distinct()
    )
    updated = open_exceptions.update(
        status=ExceptionStatus.RESOLVED,
        resolution=resolution,
        resolved_at=now,
        updated_at=now,
    )
    for appointment_id in appointment_ids:
        appointment = Appointment.objects.filter(pk=appointment_id).first()
        if appointment is None:
            logger.warning(
                f"Skip exception flag recompute; appointment {appointment_id} missing."
            )
            continue
        recompute_appointment_exception_flag(appointment)
    return updated


def acknowledge_exception(exception: AppointmentException, actor) -> AppointmentException:
    now = timezone.now()
    exception.status = ExceptionStatus.RESOLVED
    exception.resolution = ExceptionResolution.ACKNOWLEDGED
    exception.resolved_at = now
    exception.save(
        update_fields=["status", "resolution", "resolved_at", "updated_at"]
    )
    recompute_appointment_exception_flag(exception.appointment)
    AppointmentAuditLog.objects.create(
        appointment=exception.appointment,
        actor=actor,
        action=AppointmentAuditAction.EXCEPTION_ACKNOWLEDGE,
        note=exception.source_label[:500],
    )
    return exception


def load_source_instance(source_type: str, source_id):
    model = SOURCE_MODEL_MAP.get(source_type)
    if model is None:
        return None
    return model.objects.filter(pk=source_id).first()


def recurring_scan_date_range(source):
    today = timezone.localdate()
    query_start = today
    query_end = today + timedelta(days=RECURRING_SCAN_HORIZON_DAYS)
    effective_from = getattr(source, "effective_from", None)
    effective_until = getattr(source, "effective_until", None)
    if effective_from and effective_from > query_start:
        query_start = effective_from
    if effective_until and effective_until < query_end:
        query_end = effective_until
    if query_start > query_end:
        return None, None
    return query_start, query_end


def expand_source_intervals(source_type: str, source, center: Center) -> list[tuple]:
    timezone_name = get_center_timezone_name(center)
    if source_type == ExceptionSourceType.ASSOCIATE_LEAVE:
        if not source.is_active:
            return []
        return [(source.start_datetime, source.end_datetime)]

    if source_type in {
        ExceptionSourceType.ASSOCIATE_BLOCK,
        ExceptionSourceType.CARE_TEAM_BLOCK,
    }:
        if not source.is_active:
            return []
        if source.is_recurring:
            query_start, query_end = recurring_scan_date_range(source)
            if query_start is None:
                return []
            return expand_recurring_block(source, query_start, query_end, timezone_name)
        if source.start_datetime and source.end_datetime:
            return [(source.start_datetime, source.end_datetime)]
        return []

    if source_type in {ExceptionSourceType.ROOM_BLOCK, ExceptionSourceType.EQUIPMENT_BLOCK}:
        if not source.is_active:
            return []
        if source.is_recurring:
            query_start, query_end = recurring_scan_date_range(source)
            if query_start is None:
                return []
            return expand_recurring_block(source, query_start, query_end, timezone_name)
        if source.date and source.start_time and source.end_time:
            return [
                local_day_window(
                    source.date,
                    source.start_time,
                    source.end_time,
                    timezone_name,
                )
            ]
        return []

    if source_type in {
        ExceptionSourceType.ROOM_DOWNTIME,
        ExceptionSourceType.EQUIPMENT_DOWNTIME,
    }:
        if not source.is_active:
            return []
        if source.date and source.start_time and source.end_time:
            return [
                local_day_window(
                    source.date,
                    source.start_time,
                    source.end_time,
                    timezone_name,
                )
            ]
        return []

    if source_type == ExceptionSourceType.CLOSURE:
        if not source.is_active:
            return []
        return [full_day_interval(source.date, timezone_name)]

    return []


def build_source_snapshot(source_type: str, source, interval_start, interval_end) -> dict:
    label = getattr(source, "reason", "") or ""
    if source_type == ExceptionSourceType.CLOSURE:
        label = source.reason or source.get_type_display()
    return {
        "source_type": source_type,
        "source_id": source.pk,
        "source_label": label,
        "source_start_datetime": interval_start,
        "source_end_datetime": interval_end,
    }


def appointment_filter_for_source(source_type: str, source):
    if source_type == ExceptionSourceType.ASSOCIATE_LEAVE:
        return models.Q(associate_links__associate_id=source.associate_id)
    if source_type == ExceptionSourceType.ASSOCIATE_BLOCK:
        return models.Q(associate_links__associate_id=source.associate_id)
    if source_type == ExceptionSourceType.CARE_TEAM_BLOCK:
        # Team-stamped appointments only — solo member apts stay quiet.
        # Slot/calendar still subtract team blocks from live member free windows.
        return models.Q(care_team=source.care_team)
    if source_type == ExceptionSourceType.ROOM_BLOCK:
        return models.Q(room_id=source.room_id)
    if source_type == ExceptionSourceType.EQUIPMENT_BLOCK:
        return models.Q(equipment_id=source.equipment_id)
    if source_type == ExceptionSourceType.ROOM_DOWNTIME:
        return models.Q(room_id=source.room_id)
    if source_type == ExceptionSourceType.EQUIPMENT_DOWNTIME:
        return models.Q(equipment_id=source.equipment_id)
    if source_type == ExceptionSourceType.CLOSURE:
        return models.Q()
    return models.Q(pk__isnull=True)


def resolve_centers_for_source(source_type: str, source, center: Center | None) -> list[Center]:
    if source_type == ExceptionSourceType.ASSOCIATE_LEAVE:
        if source.scope == LeaveScope.CENTER and source.center_id:
            return list(Center.objects.filter(pk=source.center_id, is_active=True))
        if center is not None:
            return [center]
        center_ids = (
            Appointment.objects.filter(
                associate_links__associate_id=source.associate_id,
                status__in=BUSY_APPOINTMENT_STATUSES,
                exclusive_start_datetime__lt=source.end_datetime,
                exclusive_end_datetime__gt=source.start_datetime,
            )
            .values_list("center_id", flat=True)
            .distinct()
        )
        return list(Center.objects.filter(pk__in=center_ids, is_active=True))

    if source_type in {
        ExceptionSourceType.ASSOCIATE_BLOCK,
        ExceptionSourceType.CARE_TEAM_BLOCK,
    }:
        return list(Center.objects.filter(pk=source.center_id, is_active=True))

    if source_type in {
        ExceptionSourceType.ROOM_BLOCK,
        ExceptionSourceType.ROOM_DOWNTIME,
    }:
        return list(
            Center.objects.filter(pk=source.room.center_id, is_active=True)
        )

    if source_type in {
        ExceptionSourceType.EQUIPMENT_BLOCK,
        ExceptionSourceType.EQUIPMENT_DOWNTIME,
    }:
        return list(
            Center.objects.filter(pk=source.equipment.center_id, is_active=True)
        )

    if source_type == ExceptionSourceType.CLOSURE:
        return list(Center.objects.filter(pk=source.center_id, is_active=True))

    if center is not None:
        return [center]
    return []


def find_overlapping_appointments(
    center: Center,
    interval_start,
    interval_end,
    resource_filter,
):
    return (
        Appointment.objects.filter(
            center=center,
            status__in=BUSY_APPOINTMENT_STATUSES,
            exclusive_start_datetime__lt=interval_end,
            exclusive_end_datetime__gt=interval_start,
        )
        .filter(resource_filter)
        .distinct()
    )


def create_exception_for_appointment(
    appointment: Appointment,
    center: Center,
    snapshot: dict,
) -> bool:
    try:
        with transaction.atomic():
            AppointmentException.objects.create(
                appointment=appointment,
                center=center,
                source_type=snapshot["source_type"],
                source_id=snapshot["source_id"],
                source_label=snapshot["source_label"],
                source_start_datetime=snapshot["source_start_datetime"],
                source_end_datetime=snapshot["source_end_datetime"],
                status=ExceptionStatus.OPEN,
            )
            recompute_appointment_exception_flag(appointment)
    except IntegrityError:
        return False
    return True


def scan_source_intervals(
    source_type: str,
    source,
    center: Center,
) -> int:
    if not getattr(source, "is_active", True):
        return 0
    intervals = expand_source_intervals(source_type, source, center)
    resource_filter = appointment_filter_for_source(source_type, source)
    created_count = 0
    conflicted_appointment_ids = set()
    for interval_start, interval_end in intervals:
        snapshot_base = build_source_snapshot(
            source_type,
            source,
            interval_start,
            interval_end,
        )
        appointments = find_overlapping_appointments(
            center,
            interval_start,
            interval_end,
            resource_filter,
        )
        for appointment in appointments:
            conflicted_appointment_ids.add(appointment.pk)
            if create_exception_for_appointment(appointment, center, snapshot_base):
                created_count += 1
    reconcile_stale_source_exceptions(
        source_type,
        source,
        center,
        conflicted_appointment_ids,
    )
    return created_count


def reconcile_stale_source_exceptions(
    source_type: str,
    source,
    center: Center,
    conflicted_appointment_ids,
):
    now = timezone.now()
    stale_exceptions = AppointmentException.objects.filter(
        center=center,
        source_type=source_type,
        source_id=source.pk,
        status=ExceptionStatus.OPEN,
    ).exclude(appointment_id__in=conflicted_appointment_ids)
    appointment_ids_to_recompute = list(
        stale_exceptions.values_list("appointment_id", flat=True).distinct()
    )
    stale_exceptions.update(
        status=ExceptionStatus.RESOLVED,
        resolution=ExceptionResolution.BLOCKER_CLEARED,
        resolved_at=now,
        updated_at=now,
    )
    for appointment_id in appointment_ids_to_recompute:
        appointment = Appointment.objects.filter(pk=appointment_id).first()
        if appointment is not None:
            recompute_appointment_exception_flag(appointment)


def detect_and_reconcile_roster_exceptions(center: Center, associate_id) -> int:
    """
    Find busy appointments outside (center hours ∩ roster − blocks − leaves −
    closures) after a roster shrink/deactivate. Create open associate_roster
    exceptions; clear open ones that no longer conflict.
    """
    associate = Associate.objects.filter(pk=associate_id, is_active=True).first()
    if associate is None:
        return 0
    timezone_name = get_center_timezone_name(center)
    query_start = timezone.localdate()
    query_end = query_start + timedelta(days=RECURRING_SCAN_HORIZON_DAYS)
    range_start, range_end = datetime_range_for_dates(
        query_start, query_end, timezone_name
    )
    free_windows = compute_associate_free_windows(
        center,
        associate,
        query_start,
        query_end,
        timezone_name,
        {},
    )
    appointments = Appointment.objects.filter(
        center=center,
        status__in=BUSY_APPOINTMENT_STATUSES,
        associate_links__associate_id=associate_id,
        exclusive_start_datetime__lt=range_end,
        exclusive_end_datetime__gt=range_start,
    ).distinct()
    created_count = 0
    conflicted_appointment_ids = set()
    for appointment in appointments:
        if is_interval_contained_in_windows(
            appointment.exclusive_start_datetime,
            appointment.exclusive_end_datetime,
            free_windows,
        ):
            continue
        conflicted_appointment_ids.add(appointment.pk)
        snapshot = {
            "source_type": ExceptionSourceType.ASSOCIATE_ROSTER,
            "source_id": associate_id,
            "source_label": "Associate roster reduced",
            "source_start_datetime": appointment.exclusive_start_datetime,
            "source_end_datetime": appointment.exclusive_end_datetime,
        }
        if create_exception_for_appointment(appointment, center, snapshot):
            created_count += 1
    now = timezone.now()
    stale_exceptions = AppointmentException.objects.filter(
        center=center,
        source_type=ExceptionSourceType.ASSOCIATE_ROSTER,
        source_id=associate_id,
        status=ExceptionStatus.OPEN,
    ).exclude(appointment_id__in=conflicted_appointment_ids)
    appointment_ids_to_recompute = list(
        stale_exceptions.values_list("appointment_id", flat=True).distinct()
    )
    stale_exceptions.update(
        status=ExceptionStatus.RESOLVED,
        resolution=ExceptionResolution.BLOCKER_CLEARED,
        resolved_at=now,
        updated_at=now,
    )
    for appointment_id in appointment_ids_to_recompute:
        appointment = Appointment.objects.filter(pk=appointment_id).first()
        if appointment is not None:
            recompute_appointment_exception_flag(appointment)
    return created_count


def trigger_roster_exception_detection(center: Center, associate) -> dict:
    enqueue_exception_scan(
        center,
        ExceptionSourceType.ASSOCIATE_ROSTER,
        associate.pk,
    )
    invalidate_operations_cache(center.pk)
    return {"exception_scan": "queued"}


def detect_exceptions_for_source(
    source_type: str,
    source_id,
    *,
    sync: bool = True,
    center: Center | None = None,
) -> int:
    mode = "sync" if sync else "async"
    if source_type == ExceptionSourceType.ASSOCIATE_ROSTER:
        if center is None:
            return 0
        created = detect_and_reconcile_roster_exceptions(center, source_id)
        if created:
            record_exceptions_detected(
                center.pk,
                source_type,
                mode,
                created,
            )
        return created
    source = load_source_instance(source_type, source_id)
    if source is None:
        return 0
    centers = resolve_centers_for_source(source_type, source, center)
    total_created = 0
    for scan_center in centers:
        created = scan_source_intervals(source_type, source, scan_center)
        total_created += created
        if created:
            record_exceptions_detected(
                scan_center.pk,
                source_type,
                mode,
                created,
            )
    return total_created


def detect_exceptions_for_appointment(appointment: Appointment) -> int:
    center = appointment.center
    total_created = 0
    associate_ids = list(
        appointment.associate_links.values_list("associate_id", flat=True)
    )

    leave_filter = models.Q(associate_id__in=associate_ids, is_active=True)
    leave_filter &= models.Q(
        models.Q(scope=LeaveScope.ALL_CENTERS)
        | models.Q(scope=LeaveScope.CENTER, center=center)
    )
    for leave in AssociateLeave.objects.filter(leave_filter):
        if datetimes_overlap(
            appointment.exclusive_start_datetime,
            appointment.exclusive_end_datetime,
            leave.start_datetime,
            leave.end_datetime,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.ASSOCIATE_LEAVE,
                leave.pk,
                sync=True,
                center=center,
            )

    for block in AssociateAvailabilityBlock.objects.filter(
        center=center,
        associate_id__in=associate_ids,
        is_active=True,
    ):
        total_created += detect_exceptions_for_source(
            ExceptionSourceType.ASSOCIATE_BLOCK,
            block.pk,
            sync=True,
            center=center,
        )

    associates = [
        link.associate
        for link in appointment.associate_links.select_related("associate").all()
    ]
    team_ids = set()
    if associates:
        memberships = list(
            CenterCareTeamMember.objects.filter(
                associate__in=associates,
                care_team__center=center,
                care_team__is_active=True,
            ).select_related("care_team", "role", "associate")
        )
        for member in members_with_live_center_role(center, memberships):
            team_ids.add(member.care_team.pk)
    if appointment.care_team_id:
        team_ids.add(appointment.care_team_id)
    if team_ids:
        for block in CareTeamAvailabilityBlock.objects.filter(
            center=center,
            care_team_id__in=team_ids,
            care_team__is_active=True,
            is_active=True,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.CARE_TEAM_BLOCK,
                block.pk,
                sync=True,
                center=center,
            )

    if appointment.room_id:
        for block in RoomAvailabilityBlock.objects.filter(
            room_id=appointment.room_id,
            is_active=True,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.ROOM_BLOCK,
                block.pk,
                sync=True,
                center=center,
            )
        for downtime in RoomDowntime.objects.filter(
            room_id=appointment.room_id,
            is_active=True,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.ROOM_DOWNTIME,
                downtime.pk,
                sync=True,
                center=center,
            )

    if appointment.equipment_id:
        for block in EquipmentAvailabilityBlock.objects.filter(
            equipment_id=appointment.equipment_id,
            is_active=True,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.EQUIPMENT_BLOCK,
                block.pk,
                sync=True,
                center=center,
            )
        for downtime in EquipmentDowntime.objects.filter(
            equipment_id=appointment.equipment_id,
            is_active=True,
        ):
            total_created += detect_exceptions_for_source(
                ExceptionSourceType.EQUIPMENT_DOWNTIME,
                downtime.pk,
                sync=True,
                center=center,
            )

    timezone_name = get_center_timezone_name(center)
    appointment_date = appointment.start_datetime.astimezone(
        ZoneInfo(timezone_name)
    ).date()
    for closure in CenterClosure.objects.filter(
        center=center,
        date=appointment_date,
        is_active=True,
    ):
        total_created += detect_exceptions_for_source(
            ExceptionSourceType.CLOSURE,
            closure.pk,
            sync=True,
            center=center,
        )

    return total_created


def enqueue_exception_scan(
    center: Center,
    source_type: str,
    source_id,
) -> AppointmentExceptionScanJob:
    return AppointmentExceptionScanJob.objects.create(
        center=center,
        source_type=source_type,
        source_id=source_id,
        status=ExceptionScanJobStatus.PENDING,
    )


def process_pending_exception_scans(limit: int = 50) -> int:
    jobs = list(
        AppointmentExceptionScanJob.objects.filter(
            status=ExceptionScanJobStatus.PENDING,
        )
        .select_related("center")
        .order_by("created_at")[:limit]
    )
    processed = 0
    for job in jobs:
        job.status = ExceptionScanJobStatus.PROCESSING
        job.save(update_fields=["status", "updated_at"])
        try:
            detect_exceptions_for_source(
                job.source_type,
                job.source_id,
                sync=False,
                center=job.center,
            )
            job.status = ExceptionScanJobStatus.COMPLETED
        except (
            IntegrityError,
            ObjectDoesNotExist,
            ZoneInfoNotFoundError,
            ValueError,
        ) as exc:
            logger.exception(
                f"Exception scan job {job.pk} failed "
                f"source_type={job.source_type} source_id={job.source_id} "
                f"center={job.center_id}: {exc}"
            )
            job.status = ExceptionScanJobStatus.FAILED
        job.save(update_fields=["status", "updated_at"])
        processed += 1
    return processed


def source_is_recurring(source_type: str, source) -> bool:
    if source_type in {
        ExceptionSourceType.ASSOCIATE_BLOCK,
        ExceptionSourceType.CARE_TEAM_BLOCK,
        ExceptionSourceType.ROOM_BLOCK,
        ExceptionSourceType.EQUIPMENT_BLOCK,
    }:
        return bool(getattr(source, "is_recurring", False))
    return False


def trigger_exception_detection(
    center: Center,
    source_type: str,
    source_id,
    *,
    force_async: bool = False,
) -> dict:
    source = load_source_instance(source_type, source_id)
    if source is None or not getattr(source, "is_active", True):
        return {"exception_scan": "skipped"}
    if force_async or source_is_recurring(source_type, source):
        enqueue_exception_scan(center, source_type, source_id)
        return {"exception_scan": "queued"}
    detect_exceptions_for_source(
        source_type,
        source_id,
        sync=True,
        center=center,
    )
    return {"exception_scan": "completed"}


def trigger_exception_resolution(
    source_type: str,
    source_id,
) -> int:
    return resolve_exceptions_for_source(
        source_type,
        source_id,
        ExceptionResolution.BLOCKER_CLEARED,
    )


WINDOW_PATCH_FIELDS = {
    "effective_from",
    "effective_until",
    "start_datetime",
    "end_datetime",
    "start_time",
    "end_time",
    "date",
    "day_of_week",
    "recurring_start_time",
    "recurring_end_time",
}


def should_run_detection_on_patch(source_type: str, source, validated_data: dict) -> bool:
    if validated_data.get("is_active") is True:
        return True
    return any(field in validated_data for field in WINDOW_PATCH_FIELDS)


def should_resolve_on_patch(validated_data: dict) -> bool:
    return validated_data.get("is_active") is False


INSTANCE_SOURCE_TYPE_MAP = {
    AssociateLeave: ExceptionSourceType.ASSOCIATE_LEAVE,
    AssociateAvailabilityBlock: ExceptionSourceType.ASSOCIATE_BLOCK,
    CareTeamAvailabilityBlock: ExceptionSourceType.CARE_TEAM_BLOCK,
    RoomAvailabilityBlock: ExceptionSourceType.ROOM_BLOCK,
    EquipmentAvailabilityBlock: ExceptionSourceType.EQUIPMENT_BLOCK,
    RoomDowntime: ExceptionSourceType.ROOM_DOWNTIME,
    EquipmentDowntime: ExceptionSourceType.EQUIPMENT_DOWNTIME,
    CenterClosure: ExceptionSourceType.CLOSURE,
}


def get_source_type_for_instance(instance) -> str | None:
    return INSTANCE_SOURCE_TYPE_MAP.get(type(instance))


def pick_exception_scan_status(scan_results) -> str | None:
    statuses = [
        result["exception_scan"]
        for result in scan_results
        if result and result.get("exception_scan")
    ]
    if not statuses:
        return None
    if "queued" in statuses:
        return "queued"
    return statuses[0]


def apply_availability_exception_hooks(
    center: Center,
    instance,
    source_type: str,
    validated_data: dict | None = None,
    *,
    created: bool = False,
) -> dict | None:
    validated_data = validated_data or {}
    if not created and should_resolve_on_patch(validated_data):
        trigger_exception_resolution(source_type, instance.pk)
        invalidate_operations_cache(center.pk)
        return {"exception_scan": "resolved"}
    if created or should_run_detection_on_patch(source_type, instance, validated_data):
        force_async = created and source_is_recurring(source_type, instance)
        result = trigger_exception_detection(
            center,
            source_type,
            instance.pk,
            force_async=force_async,
        )
        invalidate_operations_cache(center.pk)
        return result
    return None
