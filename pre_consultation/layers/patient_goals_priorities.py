"""Layer 10 — ranked health goals; advances to patient_health_map on save."""

from django.utils import timezone
from rest_framework import serializers

from pre_consultation.models import PreConsultationHealthGoal, PreConsultationSession
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.directive import (
    get_directive_health_goals,
    get_health_goal_count,
    get_valid_health_goal_ids,
)


class PatientGoalsPrioritiesGoalRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    priority = serializers.IntegerField(min_value=1)


def _goals_non_field_error(message: str) -> serializers.ValidationError:
    return serializers.ValidationError({"non_field_errors": [message]})


class PatientGoalsPrioritiesRequestSerializer(serializers.Serializer):
    def run_validation(self, data=serializers.empty):
        if data is serializers.empty:
            raise _goals_non_field_error("Request body is required.")

        if not isinstance(data, list):
            raise _goals_non_field_error("Expected a JSON array.")

        goal_serializer = PatientGoalsPrioritiesGoalRequestSerializer(
            data=data,
            many=True,
        )
        goal_serializer.is_valid(raise_exception=True)
        validate_health_goal_selections(goal_serializer.validated_data)
        return goal_serializer.validated_data


class PatientGoalsPrioritiesGoalResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    priority = serializers.IntegerField(allow_null=True)


class PatientGoalsPrioritiesResponseSerializer(serializers.Serializer):
    max_health_goal_count = serializers.IntegerField()
    health_goals = PatientGoalsPrioritiesGoalResponseSerializer(many=True)
    previous_layer = serializers.CharField()


class PatientGoalsPrioritiesV2ResponseSerializer(serializers.Serializer):
    max_health_goal_count = serializers.IntegerField()
    health_goals = PatientGoalsPrioritiesGoalResponseSerializer(many=True)


def resolve_previous_layer_for_session(session: PreConsultationSession) -> str:
    from pre_consultation.cluster_probe_session import session_requires_cluster_probe

    if session_requires_cluster_probe(session):
        return PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE
    return PreConsultationLayerProgression.PATIENT_LIFESTYLE_ENVIRONMENT


def validate_health_goal_selections(health_goal_selections: list[dict]) -> list[dict]:
    max_health_goal_count = get_health_goal_count()
    valid_health_goal_ids = get_valid_health_goal_ids()
    selection_count = len(health_goal_selections)

    if selection_count < 1:
        raise _goals_non_field_error("At least one health goal is required.")

    if selection_count > max_health_goal_count:
        raise _goals_non_field_error(
            f"At most {max_health_goal_count} health goals are allowed."
        )

    submitted_goal_ids = [selection["id"] for selection in health_goal_selections]
    submitted_goal_id_set = set(submitted_goal_ids)
    if len(submitted_goal_ids) != len(submitted_goal_id_set):
        raise _goals_non_field_error("Duplicate health goal ids are not allowed.")

    invalid_goal_ids = submitted_goal_id_set - valid_health_goal_ids
    if invalid_goal_ids:
        invalid_list = ", ".join(sorted(invalid_goal_ids))
        raise _goals_non_field_error(f"Invalid health goal ids: {invalid_list}")

    submitted_priorities = [
        selection["priority"] for selection in health_goal_selections
    ]
    submitted_priority_set = set(submitted_priorities)
    expected_priorities = set(range(1, selection_count + 1))
    if submitted_priority_set != expected_priorities:
        raise _goals_non_field_error(
            f"priority values must be exactly 1 through {selection_count}."
        )

    return health_goal_selections


def build_priority_by_goal_id(stored_health_goals: list[dict]) -> dict[str, int]:
    priority_by_goal_id = {}
    for stored_health_goal in stored_health_goals:
        goal_id = stored_health_goal.get("goal_id")
        priority = stored_health_goal.get("priority")
        if isinstance(goal_id, str) and isinstance(priority, int):
            priority_by_goal_id[goal_id] = priority
    return priority_by_goal_id


def get_session_stored_health_goals(session: PreConsultationSession) -> list[dict]:
    return [
        {"goal_id": health_goal.goal_id, "priority": health_goal.priority}
        for health_goal in session.health_goals.order_by("priority")
    ]


def build_health_goals_response(stored_health_goals: list[dict]) -> list[dict]:
    priority_by_goal_id = build_priority_by_goal_id(stored_health_goals)
    return [
        {
            "id": health_goal["id"],
            "label": health_goal["label"],
            "priority": priority_by_goal_id.get(health_goal["id"]),
        }
        for health_goal in get_directive_health_goals()
    ]


def load_patient_goals_priorities_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    return {
        "max_health_goal_count": get_health_goal_count(),
        "health_goals": build_health_goals_response(
            get_session_stored_health_goals(session)
        ),
        "previous_layer": resolve_previous_layer_for_session(session),
    }


def load_patient_goals_priorities_v2_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    return {
        "max_health_goal_count": get_health_goal_count(),
        "health_goals": build_health_goals_response(
            get_session_stored_health_goals(session)
        ),
    }


def persist_patient_goals_priorities_payload(
    user,
    session: PreConsultationSession,
    validated_data: list[dict],
) -> None:
    session.health_goals.all().delete()
    PreConsultationHealthGoal.objects.bulk_create(
        [
            PreConsultationHealthGoal(
                session=session,
                goal_id=selection["id"],
                priority=selection["priority"],
            )
            for selection in validated_data
        ]
    )

    session.current_layer = PreConsultationLayerProgression.PATIENT_HEALTH_MAP
    session.save(update_fields=["current_layer", "updated_at"])


def persist_patient_goals_priorities_v2_payload(
    user,
    session: PreConsultationSession,
    validated_data: list[dict],
) -> None:
    session.health_goals.all().delete()
    PreConsultationHealthGoal.objects.bulk_create(
        [
            PreConsultationHealthGoal(
                session=session,
                goal_id=selection["id"],
                priority=selection["priority"],
            )
            for selection in validated_data
        ]
    )

    session.current_layer = PreConsultationLayerProgression.PATIENT_CATEGORY
    session.save(update_fields=["current_layer", "updated_at"])
