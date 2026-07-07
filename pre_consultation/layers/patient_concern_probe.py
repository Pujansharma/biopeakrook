"""Layer 5 — concern deep-dive probes; computes per-concern confidence scores."""

from rest_framework import serializers

from django.utils import timezone

from pre_consultation.models import PreConsultationSession
from pre_consultation.persistence import (
    get_medical_override_concern_ids,
    get_session_concern_ids,
    get_session_concerns_ordered,
)
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.concern_confidence_engine import (
    ConcernConfidenceEngine,
    ConcernConfidenceInput,
    ConcernConfidenceResult,
)
from pre_consultation.utils.directive import (
    get_concern_category_id_map,
    get_directive_category_label_map,
    get_directive_concern_label_map,
    get_directive_duration_impacts,
    get_directive_functional_impacts,
    get_directive_progression_impacts,
    get_valid_duration_impact_ids,
    get_valid_functional_impact_ids,
    get_valid_progression_impact_ids,
)


class PatientConcernProbeConcernRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    selected_functional_impact_id = serializers.CharField()
    selected_duration_impact_id = serializers.CharField()
    selected_progression_impact_id = serializers.CharField()

    def validate_id(self, value: str) -> str:
        session_concern_ids = self.context["session_concern_ids"]
        if value not in session_concern_ids:
            raise serializers.ValidationError(
                "Concern is not selected for this session."
            )
        return value

    def validate_selected_functional_impact_id(self, value: str) -> str:
        if value not in get_valid_functional_impact_ids():
            raise serializers.ValidationError("Invalid functional impact id.")
        return value

    def validate_selected_duration_impact_id(self, value: str) -> str:
        if value not in get_valid_duration_impact_ids():
            raise serializers.ValidationError("Invalid duration impact id.")
        return value

    def validate_selected_progression_impact_id(self, value: str) -> str:
        if value not in get_valid_progression_impact_ids():
            raise serializers.ValidationError("Invalid progression impact id.")
        return value


class PatientConcernProbeRequestSerializer(serializers.Serializer):
    concerns = PatientConcernProbeConcernRequestSerializer(many=True)


class PatientConcernProbeCategoryResponseSerializer(serializers.Serializer):
    label = serializers.CharField()


class PatientConcernProbeSelectedConcernResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected_functional_impact = serializers.CharField(allow_blank=True)
    selected_duration_impact = serializers.CharField(allow_blank=True)
    selected_progression_impact = serializers.CharField(allow_blank=True)
    category = PatientConcernProbeCategoryResponseSerializer()


class PatientConcernProbeResponseSerializer(serializers.Serializer):
    functional_impact = serializers.ListField(child=serializers.DictField())
    duration_impact = serializers.ListField(child=serializers.DictField())
    progression_impact = serializers.ListField(child=serializers.DictField())
    concerns = PatientConcernProbeSelectedConcernResponseSerializer(many=True)


CONCERN_CONFIDENCE_PROBE_FLAG_SCORE_MIN = 65
CONCERN_CONFIDENCE_PROBE_FLAG_SCORE_MAX = 80


def sort_concern_confidence_desc(concern_confidence: list[dict]) -> list[dict]:
    return sorted(
        concern_confidence,
        key=lambda concern_confidence_row: concern_confidence_row["final_score"],
        reverse=True,
    )


def is_probe_flagged_final_score(final_score: int) -> bool:
    return (
        CONCERN_CONFIDENCE_PROBE_FLAG_SCORE_MIN
        <= final_score
        <= CONCERN_CONFIDENCE_PROBE_FLAG_SCORE_MAX
    )


def serialize_concern_confidence_result(result: ConcernConfidenceResult) -> dict:
    return {
        "concern_id": result.concern_id,
        "signal_score": result.signal_score,
        "impact_score": result.impact_score,
        "duration_score": result.duration_score,
        "progression_score": result.progression_score,
        "raw_score": result.raw_score,
        "medical_override": result.medical_override,
        "final_score": result.final_score,
        "bucket_id": result.bucket_id,
        "bucket_label": result.bucket_label,
    }


def build_concern_confidence_results(session: PreConsultationSession) -> list[dict]:
    engine = ConcernConfidenceEngine()
    medical_override_concern_ids = get_medical_override_concern_ids(session)
    concern_confidence = []
    for concern_record in get_session_concerns_ordered(session):
        concern_source_ids = list(
            concern_record.sources.values_list("source_id", flat=True)
        )
        confidence_input = ConcernConfidenceInput(
            concern_id=concern_record.concern_id,
            concern_source_ids=concern_source_ids,
            functional_impact_id=concern_record.functional_impact_id or None,
            duration_impact_id=concern_record.duration_impact_id or None,
            progression_impact_id=concern_record.progression_impact_id or None,
            medical_override=concern_record.concern_id in medical_override_concern_ids,
        )
        concern_confidence.append(
            serialize_concern_confidence_result(engine.compute(confidence_input))
        )
    return sort_concern_confidence_desc(concern_confidence)


def build_patient_concern_probe_payload(session: PreConsultationSession) -> dict:
    concern_label_map = get_directive_concern_label_map()
    category_label_map = get_directive_category_label_map()
    concern_category_id_map = get_concern_category_id_map()
    concerns = []
    for concern_record in get_session_concerns_ordered(session):
        category_id = concern_category_id_map[concern_record.concern_id]
        concerns.append(
            {
                "id": concern_record.concern_id,
                "label": concern_label_map[concern_record.concern_id],
                "selected_functional_impact": concern_record.functional_impact_id or "",
                "selected_duration_impact": concern_record.duration_impact_id or "",
                "selected_progression_impact": (
                    concern_record.progression_impact_id or ""
                ),
                "category": {
                    "label": category_label_map[category_id],
                },
            }
        )
    return {
        "functional_impact": get_directive_functional_impacts(),
        "duration_impact": get_directive_duration_impacts(),
        "progression_impact": get_directive_progression_impacts(),
        "concerns": concerns,
    }


def load_patient_concern_probe_payload(user, session: PreConsultationSession) -> dict:
    return build_patient_concern_probe_payload(session)


def build_patient_concern_probe_put_context(session, request) -> dict:
    return {"session_concern_ids": get_session_concern_ids(session)}


def update_concern_probe_scores_for_session(session: PreConsultationSession) -> None:
    concern_confidence_results = build_concern_confidence_results(session)
    for concern_confidence_row in concern_confidence_results:
        session.concerns.filter(
            concern_id=concern_confidence_row["concern_id"],
        ).update(
            confidence_score=concern_confidence_row["final_score"],
            probe_flagged=is_probe_flagged_final_score(
                concern_confidence_row["final_score"]
            ),
            updated_at=timezone.now(),
        )


def persist_patient_concern_probe_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    for concern_data in validated_data["concerns"]:
        session.concerns.filter(concern_id=concern_data["id"]).update(
            functional_impact_id=concern_data["selected_functional_impact_id"],
            duration_impact_id=concern_data["selected_duration_impact_id"],
            progression_impact_id=concern_data["selected_progression_impact_id"],
            updated_at=timezone.now(),
        )

    update_concern_probe_scores_for_session(session)

    session.current_layer = (
        PreConsultationLayerProgression.PATIENT_MEDICAL_HISTORY_CONTEXT
    )
    session.save(update_fields=["current_layer", "updated_at"])
