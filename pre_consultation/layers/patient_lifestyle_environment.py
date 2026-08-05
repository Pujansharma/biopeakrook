"""Layer 8 — lifestyle answers; triggers lifestyle + cluster score computation."""

from django.utils import timezone
from rest_framework import serializers

from pre_consultation.cluster_scoring import (
    build_cluster_score_response,
    persist_session_cluster_scores,
)
from pre_consultation.layers.reset import clear_session_cluster_probe_answers
from pre_consultation.models import (
    PreConsultationLifestyleAnswer,
    PreConsultationSession,
)
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.directive import (
    get_directive_lifestyle_fields,
    get_valid_lifestyle_field_ids,
    get_valid_lifestyle_option_values_by_field_id,
)


class PatientLifestyleEnvironmentOptionResponseSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    selected = serializers.BooleanField()


class PatientLifestyleEnvironmentFieldResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    options = PatientLifestyleEnvironmentOptionResponseSerializer(many=True)


class PatientLifestyleEnvironmentClusterLifestyleResponseSerializer(
    serializers.Serializer
):
    cluster_id = serializers.CharField()
    cluster_label = serializers.CharField()
    lifestyle_signal_count = serializers.IntegerField()
    lifestyle_signals_triggered = serializers.ListField(child=serializers.CharField())
    lifestyle_contribution = serializers.IntegerField()


class PatientLifestyleEnvironmentClusterConfidenceResponseSerializer(
    serializers.Serializer
):
    cluster_id = serializers.CharField()
    cluster_label = serializers.CharField()
    base_concern_contribution = serializers.IntegerField()
    family_risk_contribution = serializers.IntegerField()
    lifestyle_contribution = serializers.IntegerField()
    provisional_score = serializers.IntegerField()
    validation_probed = serializers.BooleanField()
    validation_contribution = serializers.IntegerField()
    validation_skip_reason = serializers.CharField(allow_null=True)
    final_score = serializers.IntegerField()
    bucket_id = serializers.CharField()
    bucket_label = serializers.CharField()


class PatientLifestyleEnvironmentResponseSerializer(serializers.Serializer):
    lifestyle_field = PatientLifestyleEnvironmentFieldResponseSerializer(many=True)
    cluster_lifestyle = PatientLifestyleEnvironmentClusterLifestyleResponseSerializer(
        many=True
    )
    cluster_confidence = PatientLifestyleEnvironmentClusterConfidenceResponseSerializer(
        many=True
    )


class PatientLifestyleEnvironmentPutResponseSerializer(serializers.Serializer):
    next_layer = serializers.CharField()


CLUSTER_CONFIDENCE_PROBE_SCORE_MIN = 65
CLUSTER_CONFIDENCE_PROBE_SCORE_MAX = 80


class PatientLifestyleEnvironmentRequestSerializer(serializers.Serializer):
    def run_validation(self, data=serializers.empty):
        if data is serializers.empty:
            raise serializers.ValidationError(
                {"non_field_errors": ["Request body is required."]}
            )

        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Expected a JSON object."]}
            )

        validate_lifestyle_answers(data)
        return data


def validate_lifestyle_answers(lifestyle_answers: dict[str, str]) -> dict[str, str]:
    valid_lifestyle_field_ids = get_valid_lifestyle_field_ids()
    valid_option_values_by_field_id = get_valid_lifestyle_option_values_by_field_id()

    submitted_field_ids = set(lifestyle_answers)
    missing_field_ids = valid_lifestyle_field_ids - submitted_field_ids
    if missing_field_ids:
        raise serializers.ValidationError(
            {
                field_id: "This field is required."
                for field_id in sorted(missing_field_ids)
            }
        )

    extra_field_ids = submitted_field_ids - valid_lifestyle_field_ids
    if extra_field_ids:
        raise serializers.ValidationError(
            {
                field_id: "Unknown lifestyle field."
                for field_id in sorted(extra_field_ids)
            }
        )

    for field_id, option_value in lifestyle_answers.items():
        if not isinstance(option_value, str):
            raise serializers.ValidationError(
                {field_id: "Option value must be a string."}
            )
        valid_option_values = valid_option_values_by_field_id[field_id]
        if option_value not in valid_option_values:
            raise serializers.ValidationError(
                {
                    field_id: (
                        f"Invalid option value '{option_value}' for field '{field_id}'."
                    )
                }
            )

    return lifestyle_answers


def build_lifestyle_field_response(
    selected_lifestyle_answers: dict[str, str],
) -> list[dict]:
    lifestyle_fields = []
    for lifestyle_field in get_directive_lifestyle_fields():
        selected_option_value = selected_lifestyle_answers.get(lifestyle_field["id"])
        lifestyle_fields.append(
            {
                "id": lifestyle_field["id"],
                "label": lifestyle_field["label"],
                "options": [
                    {
                        "value": option["value"],
                        "label": option["label"],
                        "selected": option["value"] == selected_option_value,
                    }
                    for option in lifestyle_field["options"]
                ],
            }
        )
    return lifestyle_fields


def get_session_lifestyle_answers(session: PreConsultationSession) -> dict[str, str]:
    return {
        answer.field_id: answer.option_value
        for answer in session.lifestyle_answers.order_by("created_at")
    }


def is_cluster_probe_flagged_final_score(final_score: int) -> bool:
    return (
        CLUSTER_CONFIDENCE_PROBE_SCORE_MIN
        <= final_score
        <= CLUSTER_CONFIDENCE_PROBE_SCORE_MAX
    )


def get_probe_flagged_cluster_ids(session: PreConsultationSession) -> set[str]:
    return {
        cluster_score.cluster_id
        for cluster_score in session.cluster_scores.all()
        if is_cluster_probe_flagged_final_score(cluster_score.final_score)
    }


def resolve_next_layer_from_cluster_confidence(
    session: PreConsultationSession,
) -> str:
    from pre_consultation.cluster_probe_session import session_requires_cluster_probe

    if session_requires_cluster_probe(session):
        return PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE
    return PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES


def resolve_next_layer_from_cluster_confidence_v2(
    session: PreConsultationSession,
) -> str:
    from pre_consultation.cluster_probe_session import session_requires_cluster_probe

    if session_requires_cluster_probe(session):
        return PreConsultationLayerProgression.PATIENT_CLUSTER_PROBE
    return PreConsultationLayerProgression.PATIENT_HEALTH_MAP


def load_patient_lifestyle_environment_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    return {
        "lifestyle_field": build_lifestyle_field_response(
            get_session_lifestyle_answers(session)
        ),
        **build_cluster_score_response(session),
    }


def load_patient_lifestyle_environment_put_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    return {
        "next_layer": resolve_next_layer_from_cluster_confidence(session),
    }


def load_patient_lifestyle_environment_v2_put_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    return {
        "next_layer": resolve_next_layer_from_cluster_confidence_v2(session),
    }


def write_patient_lifestyle_environment_answers(
    session: PreConsultationSession,
    validated_data: dict,
) -> None:
    clear_session_cluster_probe_answers(session)
    session.lifestyle_answers.all().delete()
    PreConsultationLifestyleAnswer.objects.bulk_create(
        [
            PreConsultationLifestyleAnswer(
                session=session,
                field_id=field_id,
                option_value=option_value,
            )
            for field_id, option_value in validated_data.items()
        ]
    )
    persist_session_cluster_scores(session, validated_data)


def persist_patient_lifestyle_environment_payload(
    user,
    session: PreConsultationSession,
    validated_data: dict,
) -> None:
    write_patient_lifestyle_environment_answers(session, validated_data)

    session.current_layer = resolve_next_layer_from_cluster_confidence(session)
    session.updated_at = timezone.now()
    session.save(update_fields=["current_layer", "updated_at"])


def persist_patient_lifestyle_environment_v2_payload(
    user,
    session: PreConsultationSession,
    validated_data: dict,
) -> None:
    write_patient_lifestyle_environment_answers(session, validated_data)

    session.current_layer = resolve_next_layer_from_cluster_confidence_v2(session)
    session.updated_at = timezone.now()
    session.save(update_fields=["current_layer", "updated_at"])
