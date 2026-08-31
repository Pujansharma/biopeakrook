import logging

logger = logging.getLogger("appointments")

_COUNTERS = {}


def _increment_counter(name, labels=None):
    key = (name, tuple(sorted((labels or {}).items())))
    _COUNTERS[key] = _COUNTERS.get(key, 0) + 1


def record_book_outcome(center_id, outcome, resource=None):
    labels = {"center_id": str(center_id), "outcome": outcome}
    if resource:
        labels["resource"] = resource
    _increment_counter("appointments_book_total", labels)


def record_lifecycle(center_id, action, status):
    _increment_counter(
        "appointments_lifecycle_total",
        {
            "center_id": str(center_id),
            "action": action,
            "status": status,
        },
    )


def record_exceptions_detected(center_id, source_type, mode, count=1):
    labels = {
        "center_id": str(center_id),
        "source_type": source_type,
        "mode": mode,
    }
    for _ in range(count):
        _increment_counter("appointments_exceptions_detected_total", labels)


def record_exceptions_open(center_id, count):
    log_appointment_event(
        "info",
        center_id=center_id,
        actor_id=None,
        action="exceptions_open_gauge",
        duration_ms=count,
    )


def record_slots_duration(center_id, duration_seconds):
    log_appointment_event(
        "info",
        center_id=center_id,
        actor_id=None,
        action="slots_find",
        duration_ms=int(duration_seconds * 1000),
    )


def record_operations_cache_hit(center_id, tab, hit):
    _increment_counter(
        "appointments_operations_cache_hit",
        {
            "center_id": str(center_id),
            "tab": tab,
            "hit": str(hit),
        },
    )


def log_appointment_event(
    level,
    center_id,
    actor_id,
    action,
    appointment_id=None,
    duration_ms=None,
):
    payload = {
        "center_id": str(center_id),
        "action": action,
    }
    if actor_id is not None:
        payload["actor_id"] = str(actor_id)
    if appointment_id is not None:
        payload["appointment_id"] = str(appointment_id)
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    log_method = getattr(logger, level, logger.info)
    log_method("appointment_event", extra=payload)
