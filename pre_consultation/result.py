"""Build the completed-session summary shown after layer 10."""

from rest_framework import serializers

from pre_consultation.layers.serialization import DirectiveJsonKeyCharField
from pre_consultation.layers.patient_goals_priorities import (
    build_health_goals_response,
    get_session_stored_health_goals,
    resolve_previous_layer_for_session,
)
from pre_consultation.layers.patient_lifestyle_environment import (
    get_session_lifestyle_answers,
)
from pre_consultation.models import PreConsultationSession
from pre_consultation.persistence import get_session_concern_ids
from pre_consultation.utils.directive import (
    get_concern_cluster_ids_map,
    get_directive_cluster_display_map,
    get_directive_lifestyle_fields,
)


class HealthSystemItemSerializer(serializers.Serializer):
    label = serializers.CharField()
    icon = serializers.CharField()
    icon_class = DirectiveJsonKeyCharField(json_key="icon-class")


class LifestyleContextItemSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()


class GoalItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    priority = serializers.IntegerField()


class PreConsultationSessionResultSerializer(serializers.Serializer):
    health_system = HealthSystemItemSerializer(many=True)
    cluster_count = serializers.IntegerField()
    concern_count = serializers.IntegerField()
    lifestyle_context = LifestyleContextItemSerializer(many=True)
    goals = GoalItemSerializer(many=True)


class PreConsultationSessionResultV2Serializer(serializers.Serializer):
    health_system = HealthSystemItemSerializer(many=True)
    cluster_count = serializers.IntegerField()
    concern_count = serializers.IntegerField()
    lifestyle_context = LifestyleContextItemSerializer(many=True)
    goals = GoalItemSerializer(many=True)
    previous_layer = serializers.CharField()


def build_lifestyle_option_label_map() -> dict[str, dict[str, str]]:
    option_label_by_field_id: dict[str, dict[str, str]] = {}
    for lifestyle_field in get_directive_lifestyle_fields():
        option_label_by_field_id[lifestyle_field["id"]] = {
            option["value"]: option["label"] for option in lifestyle_field["options"]
        }
    return option_label_by_field_id


def build_explored_cluster_ids(session: PreConsultationSession) -> list[str]:
    """Derive health-system clusters from selected concerns via directive mapping."""
    concern_cluster_ids_map = get_concern_cluster_ids_map()
    cluster_ids: set[str] = set()
    for concern_id in get_session_concern_ids(session):
        cluster_ids.update(concern_cluster_ids_map.get(concern_id, []))
    return sorted(cluster_ids)


def build_health_system_payload(cluster_ids: list[str]) -> list[dict[str, str]]:
    cluster_display_map = get_directive_cluster_display_map()
    health_system: list[dict[str, str]] = []
    for cluster_id in cluster_ids:
        cluster_display = cluster_display_map.get(cluster_id)
        if cluster_display is None:
            continue
        health_system.append(
            {
                "label": cluster_display["label"],
                "icon": cluster_display["icon"],
                "icon-class": cluster_display["icon-class"],
            }
        )
    return health_system


def build_lifestyle_context_payload(
    session: PreConsultationSession,
) -> list[dict[str, str]]:
    selected_lifestyle_answers = get_session_lifestyle_answers(session)
    if not selected_lifestyle_answers:
        return []

    option_label_by_field_id = build_lifestyle_option_label_map()
    lifestyle_context: list[dict[str, str]] = []
    for lifestyle_field in get_directive_lifestyle_fields():
        field_id = lifestyle_field["id"]
        selected_option_value = selected_lifestyle_answers.get(field_id)
        if selected_option_value is None:
            continue
        option_label = option_label_by_field_id[field_id].get(
            selected_option_value,
            selected_option_value,
        )
        lifestyle_context.append(
            {
                "label": lifestyle_field["label"],
                "value": option_label,
            }
        )
    return lifestyle_context


def build_goals_payload(session: PreConsultationSession) -> list[dict]:
    ranked_health_goals = [
        health_goal
        for health_goal in build_health_goals_response(
            get_session_stored_health_goals(session)
        )
        if health_goal["priority"] is not None
    ]
    return sorted(ranked_health_goals, key=lambda health_goal: health_goal["priority"])


def build_overview_goals_payload(session: PreConsultationSession) -> list[dict]:
    return [
        {
            "label": health_goal["label"],
            "priority": health_goal["priority"],
        }
        for health_goal in build_goals_payload(session)
    ]


def build_session_result_payload(session: PreConsultationSession) -> dict:
    explored_cluster_ids = build_explored_cluster_ids(session)
    health_system = build_health_system_payload(explored_cluster_ids)
    return {
        "health_system": health_system,
        "cluster_count": len(health_system),
        "concern_count": session.concerns.count(),
        "lifestyle_context": build_lifestyle_context_payload(session),
        "goals": build_goals_payload(session),
    }


def build_session_result_v2_payload(session: PreConsultationSession) -> dict:
    return {
        **build_session_result_payload(session),
        "previous_layer": resolve_previous_layer_for_session(session),
    }
