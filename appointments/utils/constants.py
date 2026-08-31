from django.db import models


BUSY_APPOINTMENT_STATUSES = frozenset(
    {
        "confirmed",
        "checked_in",
        "in_progress",
    }
)


class AppointmentStatus(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    CHECKED_IN = "checked_in", "Checked In"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No Show"


class AppointmentAuditAction(models.TextChoices):
    CREATE = "create", "Create"
    CHECK_IN = "check_in", "Check In"
    START = "start", "Start"
    MARK_LATE = "mark_late", "Mark Late"
    COMPLETE = "complete", "Complete"
    NO_SHOW = "no_show", "No Show"
    CANCEL = "cancel", "Cancel"
    RESCHEDULE = "reschedule", "Reschedule"
    EXCEPTION_ACKNOWLEDGE = "exception_acknowledge", "Exception Acknowledge"


class ExceptionSourceType(models.TextChoices):
    ASSOCIATE_LEAVE = "associate_leave", "Associate Leave"
    ASSOCIATE_BLOCK = "associate_block", "Associate Block"
    ROOM_BLOCK = "room_block", "Room Block"
    EQUIPMENT_BLOCK = "equipment_block", "Equipment Block"
    ROOM_DOWNTIME = "room_downtime", "Room Downtime"
    EQUIPMENT_DOWNTIME = "equipment_downtime", "Equipment Downtime"
    CLOSURE = "closure", "Closure"


class ExceptionResolution(models.TextChoices):
    CANCELLED = "cancelled", "Cancelled"
    RESCHEDULED = "rescheduled", "Rescheduled"
    BLOCKER_CLEARED = "blocker_cleared", "Blocker Cleared"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"


class ExceptionStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class ExceptionScanJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class AvailabilityGranularity(models.TextChoices):
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"


class LeaveScope(models.TextChoices):
    CENTER = "center", "Center"
    ALL_CENTERS = "all_centers", "All Centers"
