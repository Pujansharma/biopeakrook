from django.db import models


class DiagnosticOrderStatus(models.TextChoices):
    ORDER_CREATED = "order.created", "Order Created"
    TASK_CONFIRMED = "task.confirmed", "Task Confirmed"
    TASK_ASSIGNED = "task.assigned", "Task Assigned"
    TASK_ACCEPTED = "task.accepted", "Task Accepted"
    TASK_STARTED = "task.started", "Task Started"
    TASK_IN_PROGRESS = "task.in_progress", "Task In Progress"
    TASK_COMPLETED = "task.completed", "Task Completed"
    TEST_COMPLETED_SENT = "test.completed_sent", "Test Completed Sent"
    ORDER_COMPLETED = "order.completed", "Order Completed"
    ORDER_CANCELLED = "order.cancelled", "Order Cancelled"


TERMINAL_ORDER_STATUSES = (
    DiagnosticOrderStatus.ORDER_COMPLETED,
    DiagnosticOrderStatus.ORDER_CANCELLED,
)


class CatalogCategory(models.TextChoices):
    TEST = "test", "Test"
    PACKAGE = "package", "Package"


class DiagnosticCity(models.TextChoices):
    BLR = "BLR", "Bengaluru"
    DEL = "DEL", "Delhi"
    NOA = "NOA", "Noida"
    HYD = "HYD", "Hyderabad"
    MUM = "MUM", "Mumbai"
    GGN = "GGN", "Gurugram"
    PNQ = "PNQ", "Pune"


# Inclusive pincode ranges: (city_code, start, end)
PINCODE_CITY_RANGES = (
    (DiagnosticCity.BLR, 560001, 560300),
    (DiagnosticCity.BLR, 562110, 562162),
    (DiagnosticCity.DEL, 110001, 110096),
    (DiagnosticCity.NOA, 201301, 201318),
    (DiagnosticCity.HYD, 500001, 500148),
    (DiagnosticCity.MUM, 400001, 400104),
    (DiagnosticCity.GGN, 122001, 122052),
    (DiagnosticCity.PNQ, 411001, 411068),
)


class CollectionDateFilter:
    ALL = "all"
    TODAY = "today"
    TOMORROW = "tomorrow"
    PAST_7_DAYS = "past_7_days"
    UPCOMING = "upcoming"

    CHOICES = (
        ALL,
        TODAY,
        TOMORROW,
        PAST_7_DAYS,
        UPCOMING,
    )
