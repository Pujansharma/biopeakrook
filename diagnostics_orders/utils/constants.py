from django.db import models


class DiagnosticOrderStatus(models.TextChoices):
    ORDER_CREATED = "order.created", "order.created"
    TASK_CONFIRMED = "task.confirmed", "task.confirmed"
    TASK_ASSIGNED = "task.assigned", "task.assigned"
    TASK_ACCEPTED = "task.accepted", "task.accepted"
    TASK_STARTED = "task.started", "task.started"
    TASK_IN_PROGRESS = "task.in_progress", "task.in_progress"
    TASK_COMPLETED = "task.completed", "task.completed"
    TEST_COMPLETED_SENT = "test.completed_sent", "test.completed_sent"
    ORDER_COMPLETED = "order.completed", "order.completed"
    ORDER_CANCELLED = "order.cancelled", "order.cancelled"


TERMINAL_ORDER_STATUSES = (
    DiagnosticOrderStatus.ORDER_COMPLETED,
    DiagnosticOrderStatus.ORDER_CANCELLED,
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
