import math
import re
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from wearables.utils.constants import HealthDomain

PRIVATE_FIELDS = {
    "metadata",
    "metadata_info",
    "user_id",
    "client_uuid",
    "document_id",
    "event_id",
    "document_version",
    "version",
    "id",
    "_id",
    "data_structure",
    "type",
    "source",
    "data_source",
    "source_of_data",
    "source_of_data_string",
    "sources_of_data_array",
    "sources_of_data",
    "device_source_data_array",
    "measurement_types",
    "email",
    "phone",
    "phone_number",
    "access_token",
    "refresh_token",
    "session_token",
}

TIMESTAMP_FIELDS = {
    "datetime",
    "date",
    "datetime_string",
    "date_time",
    "start_datetime_string",
    "start_date_time",
    "summary_date_string",
    "last_updated_datetime_string",
    "sleep_date_string",
    "sleep_start_datetime_string",
    "activity_start_datetime_string",
    "activity_end_datetime_string",
    "period_start_date_string",
}

SELECTED_TEXT_FIELDS = {
    "activity_type_name_string",
    "workout_type_string",
}


@dataclass(frozen=True)
class ExtractedMetric:
    field_path: str
    metric: str
    domain: str
    value: float | str | bool
    unit: str


def is_private_field(field_name: str) -> bool:
    normalized = str(field_name).lower()
    return normalized in PRIVATE_FIELDS or normalized.endswith(
        ("_id", "_uuid", "_token", "_secret", "_timestamp")
    )


def terminal_field(field_path: str) -> str:
    terminal = field_path.rsplit(".", maxsplit=1)[-1]
    return re.sub(r"\[\d+\]", "", terminal)


def metric_name(field_path: str) -> str:
    field_name = terminal_field(field_path).lower()
    rules = [
        (("sleep_duration_seconds", "total_sleep_duration_seconds"), "sleep_duration_seconds"),
        (("sleep_duration_minutes", "total_sleep_duration_minutes"), "sleep_duration_seconds"),
        (("sleep_duration_hours",), "sleep_duration_seconds"),
        (("accumulated_steps", "steps_int", "total_steps", "steps"), "steps"),
        (("hr_resting", "resting_heart_rate"), "resting_heart_rate"),
        (("hr_avg", "average_heart_rate", "avg_heart_rate"), "average_heart_rate"),
        (("hr_maximum", "maximum_heart_rate", "max_heart_rate"), "maximum_heart_rate"),
        (("hrv_avg_rmssd", "hrv_rmssd", "rmssd"), "hrv_rmssd"),
        (("recovery_score",), "recovery_score"),
        (("readiness_score",), "readiness_score"),
        (("stress_avg", "average_stress", "stress_level"), "stress_level"),
        (("weight_kg", "body_weight_kg"), "weight_kg"),
        (("bmi",), "bmi"),
        (("body_fat",), "body_fat_percentage"),
        (("muscle_mass", "muscle_composition"), "muscle_mass_kg"),
        (("water_composition", "body_water"), "body_water_percentage"),
        (("activity_duration", "workout_duration"), "workout_duration_seconds"),
        (("calories_expenditure", "workout_calories"), "workout_calories_kcal"),
        (("activity_distance", "workout_distance"), "workout_distance_meters"),
        (("activity_type_name", "workout_type"), "workout_type"),
    ]
    for patterns, canonical_name in rules:
        if any(pattern in field_name for pattern in patterns):
            return canonical_name
    normalized = re.sub(
        r"_(float|int|bool|string|object|array)$",
        "",
        field_name,
    )
    return normalized[:128]


def health_domain_for(field_path: str, data_structure: str) -> str | None:
    text = f"{data_structure}.{field_path}".lower()
    if any(token in text for token in ("workout", "activity_event", "exercise_event")):
        return HealthDomain.WORKOUTS
    if any(token in text for token in ("recovery_score", "readiness_score", "stress")):
        return HealthDomain.RECOVERY
    if "sleep" in text or "time_in_bed" in text:
        return HealthDomain.SLEEP
    if any(
        token in text
        for token in (
            "weight",
            "bmi",
            "body_fat",
            "muscle",
            "water_composition",
            "lean_mass",
        )
    ):
        return HealthDomain.BODY
    if any(
        token in text
        for token in (
            "heart_rate",
            "hr_",
            "hrv",
            "rmssd",
            "sdnn",
            "rr_interval",
        )
    ):
        return HealthDomain.HEART
    if any(
        token in text
        for token in (
            "physical",
            "steps",
            "floor",
            "calorie",
            "distance",
            "active_minutes",
            "active_seconds",
        )
    ):
        return HealthDomain.ACTIVITY
    return None


def metric_unit(field_path: str, metric: str) -> str:
    field_name = terminal_field(field_path).lower()
    if metric == "sleep_duration_seconds":
        return "seconds"
    if metric == "steps":
        return "steps"
    if metric in {"resting_heart_rate", "average_heart_rate", "maximum_heart_rate"}:
        return "bpm"
    if metric == "hrv_rmssd":
        return "ms"
    if metric in {"recovery_score", "readiness_score", "stress_level"}:
        return "score"
    if metric in {"weight_kg", "muscle_mass_kg"}:
        return "kg"
    if metric in {"body_fat_percentage", "body_water_percentage"}:
        return "%"
    if metric == "bmi":
        return "kg/m²"
    if metric == "workout_duration_seconds":
        return "seconds"
    if metric == "workout_calories_kcal":
        return "kcal"
    if metric == "workout_distance_meters":
        return "meters"
    if "percentage" in field_name or "_percent" in field_name:
        return "%"
    if "_seconds" in field_name:
        return "seconds"
    if "_minutes" in field_name:
        return "minutes"
    if "_hours" in field_name:
        return "hours"
    if "_kcal" in field_name:
        return "kcal"
    if "_meters" in field_name:
        return "meters"
    return ""


def canonical_numeric_value(field_path: str, metric: str, value: float) -> float:
    field_name = terminal_field(field_path).lower()
    if metric in {"sleep_duration_seconds", "workout_duration_seconds"}:
        if "_minutes" in field_name:
            return value * 60.0
        if "_hours" in field_name:
            return value * 3600.0
    return value


def extract_metric_values(
    node: Any,
    *,
    data_structure: str,
    path: str = "",
) -> Generator[ExtractedMetric]:
    if isinstance(node, dict):
        for key, value in node.items():
            if is_private_field(key) or key in TIMESTAMP_FIELDS:
                continue
            child_path = f"{path}.{key}" if path else key
            yield from extract_metric_values(
                value,
                data_structure=data_structure,
                path=child_path,
            )
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            yield from extract_metric_values(
                value,
                data_structure=data_structure,
                path=f"{path}[{index}]",
            )
        return
    domain = health_domain_for(path, data_structure)
    if domain is None:
        return
    canonical_metric = metric_name(path)
    if isinstance(node, bool):
        yield ExtractedMetric(path, canonical_metric, domain, node, "")
        return
    if isinstance(node, (int, float)) and math.isfinite(node):
        numeric_value = canonical_numeric_value(path, canonical_metric, float(node))
        yield ExtractedMetric(
            path,
            canonical_metric,
            domain,
            numeric_value,
            metric_unit(path, canonical_metric),
        )
        return
    if isinstance(node, str) and terminal_field(path) in SELECTED_TEXT_FIELDS:
        yield ExtractedMetric(path, canonical_metric, domain, node[:512], "")


def structure_represents_workout(data_structure: str) -> bool:
    normalized = data_structure.lower()
    return any(
        token in normalized
        for token in ("activity_event", "workout", "exercise_event")
    )

