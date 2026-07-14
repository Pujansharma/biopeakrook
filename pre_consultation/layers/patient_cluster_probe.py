"""Layer 6 — cluster validation probes for probe-flagged clusters (conditional)."""

from rest_framework import serializers

from pre_consultation.cluster_scoring import persist_session_cluster_scores
from pre_consultation.layers.patient_lifestyle_environment import (
    get_probe_flagged_cluster_ids,
    get_session_lifestyle_answers,
)
from pre_consultation.models import (
    PreConsultationConcernProbeAnswer,
    PreConsultationSession,
)
from pre_consultation.persistence import (
    get_session_concern_ids,
    get_session_concerns_ordered,
)
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.directive import (
    get_cluster_probe_ids_for_concern,
    get_concern_cluster_ids_map,
    get_directive_cluster_label_map,
    get_directive_cluster_probes_for_cluster,
    get_directive_concern_label_map,
    get_valid_cluster_probe_ids_for_concern,
)
from pre_consultation.utils.engine_directive import load_directive


class PatientClusterProbeAnswerRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    value = serializers.JSONField()

    def validate_value(self, value) -> int:
        return normalize_cluster_probe_value(value)


class PatientClusterProbeConcernRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    cluster_probe = PatientClusterProbeAnswerRequestSerializer(many=True)

    def validate_id(self, value: str) -> str:
        eligible_concern_ids = self.context["cluster_probe_eligible_concern_ids"]
        if value not in eligible_concern_ids:
            raise serializers.ValidationError(
                "Concern is not eligible for cluster probe."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        concern_id = attrs["id"]
        valid_cluster_probe_ids = get_valid_cluster_probe_ids_for_concern(concern_id)
        submitted_cluster_probe_ids = [
            cluster_probe["id"] for cluster_probe in attrs["cluster_probe"]
        ]
        submitted_cluster_probe_id_set = set(submitted_cluster_probe_ids)
        if len(submitted_cluster_probe_ids) != len(submitted_cluster_probe_id_set):
            raise serializers.ValidationError(
                {"cluster_probe": "Duplicate cluster probe ids are not allowed."}
            )

        invalid_cluster_probe_ids = (
            submitted_cluster_probe_id_set - valid_cluster_probe_ids
        )
        if invalid_cluster_probe_ids:
            invalid_list = ", ".join(sorted(invalid_cluster_probe_ids))
            raise serializers.ValidationError(
                {"cluster_probe": f"Invalid ids: {invalid_list}"}
            )

        missing_cluster_probe_ids = (
            valid_cluster_probe_ids - submitted_cluster_probe_id_set
        )
        if missing_cluster_probe_ids:
            missing_list = ", ".join(sorted(missing_cluster_probe_ids))
            raise serializers.ValidationError(
                {"cluster_probe": f"Missing ids: {missing_list}"}
            )

        attrs["cluster_probe_answers"] = {
            cluster_probe["id"]: cluster_probe["value"]
            for cluster_probe in attrs["cluster_probe"]
        }
        return attrs


class PatientClusterProbeRequestSerializer(serializers.Serializer):
    concerns = PatientClusterProbeConcernRequestSerializer(many=True)


class PatientClusterProbeItemResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField(allow_null=True)


class PatientClusterProbeClusterResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    cluster_probe = PatientClusterProbeItemResponseSerializer(many=True)


class PatientClusterProbeConcernResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    cluster = PatientClusterProbeClusterResponseSerializer(many=True)


class PatientClusterProbeResponseSerializer(serializers.Serializer):
    concerns = PatientClusterProbeConcernResponseSerializer(many=True)


def normalize_cluster_probe_value(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise serializers.ValidationError("value must be 0 or 1.")

    normalized_value = str(value).strip().lower()
    if normalized_value in {"yes", "1"}:
        return 1
    if normalized_value in {"no", "0"}:
        return 0
    raise serializers.ValidationError("value must be yes, no, 1, or 0.")


def get_cluster_probe_eligible_concern_ids(
    session: PreConsultationSession,
) -> set[str]:
    flagged_cluster_ids = get_probe_flagged_cluster_ids(session)
    if not flagged_cluster_ids:
        return set()

    cluster_concern_map = load_directive().cluster_concern_map
    session_concern_ids = get_session_concern_ids(session)
    eligible_concern_ids: set[str] = set()
    for cluster_id in flagged_cluster_ids:
        cluster_concern_ids = set(cluster_concern_map.get(cluster_id, []))
        eligible_concern_ids.update(cluster_concern_ids & session_concern_ids)
    return eligible_concern_ids


def get_saved_cluster_probe_answers(concern) -> dict[str, int]:
    return {
        probe_answer.probe_id: probe_answer.value
        for probe_answer in concern.probe_answers.all()
    }


def build_probe_counts_for_concern(
    concern_id: str,
    cluster_probe_answers: dict[str, int],
) -> tuple[int, int]:
    total_probe_questions = len(get_cluster_probe_ids_for_concern(concern_id))
    total_probe_positives = sum(cluster_probe_answers.values())
    return total_probe_questions, total_probe_positives


def build_cluster_payload_for_concern(
    concern,
    concern_label_map: dict[str, str],
    cluster_label_map: dict[str, str],
    concern_cluster_ids_map: dict[str, list[str]],
) -> dict:
    saved_answers = get_saved_cluster_probe_answers(concern)
    clusters = []
    for cluster_id in concern_cluster_ids_map.get(concern.concern_id, []):
        cluster_probes = [
            {
                "id": cluster_probe["id"],
                "label": cluster_probe["label"],
                "value": saved_answers.get(cluster_probe["id"]),
            }
            for cluster_probe in get_directive_cluster_probes_for_cluster(cluster_id)
        ]
        clusters.append(
            {
                "id": cluster_id,
                "label": cluster_label_map[cluster_id],
                "cluster_probe": cluster_probes,
            }
        )
    return {
        "id": concern.concern_id,
        "label": concern_label_map[concern.concern_id],
        "cluster": clusters,
    }


def build_patient_cluster_probe_payload(session: PreConsultationSession) -> dict:
    eligible_concern_ids = get_cluster_probe_eligible_concern_ids(session)
    concern_label_map = get_directive_concern_label_map()
    cluster_label_map = get_directive_cluster_label_map()
    concern_cluster_ids_map = get_concern_cluster_ids_map()
    concerns = []
    for concern in get_session_concerns_ordered(session):
        if concern.concern_id not in eligible_concern_ids:
            continue
        concerns.append(
            build_cluster_payload_for_concern(
                concern,
                concern_label_map,
                cluster_label_map,
                concern_cluster_ids_map,
            )
        )
    return {"concerns": concerns}


def load_patient_cluster_probe_payload(user, session: PreConsultationSession) -> dict:
    return build_patient_cluster_probe_payload(session)


def build_patient_cluster_probe_put_context(session, request) -> dict:
    return {
        "cluster_probe_eligible_concern_ids": get_cluster_probe_eligible_concern_ids(
            session
        ),
    }


def write_patient_cluster_probe_answers(
    session: PreConsultationSession, validated_data: dict
) -> None:
    for concern_data in validated_data["concerns"]:
        concern = session.concerns.get(concern_id=concern_data["id"])
        cluster_probe_answers = concern_data["cluster_probe_answers"]
        concern.probe_answers.all().delete()
        PreConsultationConcernProbeAnswer.objects.bulk_create(
            [
                PreConsultationConcernProbeAnswer(
                    concern=concern,
                    probe_id=probe_id,
                    value=probe_value,
                )
                for probe_id, probe_value in cluster_probe_answers.items()
            ]
        )
        probe_question_count, probe_positive_count = build_probe_counts_for_concern(
            concern_data["id"],
            cluster_probe_answers,
        )
        concern.probe_question_count = probe_question_count
        concern.probe_positive_count = probe_positive_count
        concern.save(
            update_fields=[
                "probe_question_count",
                "probe_positive_count",
                "updated_at",
            ]
        )

    persist_session_cluster_scores(session, get_session_lifestyle_answers(session))


def persist_patient_cluster_probe_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    write_patient_cluster_probe_answers(session, validated_data)
    session.current_layer = PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES
    session.save(update_fields=["current_layer", "updated_at"])


def persist_patient_cluster_probe_v2_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    write_patient_cluster_probe_answers(session, validated_data)
    session.current_layer = PreConsultationLayerProgression.PATIENT_HEALTH_MAP
    session.save(update_fields=["current_layer", "updated_at"])
