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


# Customer list sort: in_progress → confirmed → checked_in → completed → cancelled
# (no_show last; not in the FE status strip).
CUSTOMER_APPOINTMENT_STATUS_SORT_ORDER = (
    AppointmentStatus.IN_PROGRESS,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.CHECKED_IN,
    AppointmentStatus.COMPLETED,
    AppointmentStatus.CANCELLED,
    AppointmentStatus.NO_SHOW,
)


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
    ASSOCIATE_ROSTER = "associate_roster", "Associate Roster"
    CARE_TEAM_BLOCK = "care_team_block", "Care Team Block"
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


class AvailabilityOrigin(models.TextChoices):
    MANUAL = "manual", "Manual"
    GOOGLE = "google", "Google"


ROSTER_HOURS_ERROR = "Roster must fall within center operating hours."
OPERATING_HOURS_ROSTER_ERROR = "Operating hours conflict with existing staff roster."

BEFORE_OPENING = "before_opening"
AFTER_CLOSING = "after_closing"
CENTER_CLOSED = "center_closed"
CENTER_HOURS_MISSING = "center_hours_missing"
ROSTER_ON_CLOSED_DAY = "roster_on_closed_day"

BEFORE_OPENING_MESSAGE = "Starts before center opening time."
AFTER_CLOSING_MESSAGE = "Ends after center closing time."
CENTER_CLOSED_MESSAGE = "Center is closed on this day."
CENTER_HOURS_MISSING_MESSAGE = "Center operating hours are not set for this day."
ROSTER_BEFORE_NEW_OPENING_MESSAGE = "Active roster starts before the new opening time."
ROSTER_AFTER_NEW_CLOSING_MESSAGE = "Active roster ends after the new closing time."
ROSTER_ON_CLOSED_DAY_MESSAGE = "Active roster exists on a day being closed."

UNAVAILABLE_DAY_ERROR = {
    True: (CENTER_CLOSED, CENTER_CLOSED_MESSAGE),
    False: (CENTER_HOURS_MISSING, CENTER_HOURS_MISSING_MESSAGE),
}
