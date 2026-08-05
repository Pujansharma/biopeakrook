"""Merged patient_symptom + patient_concern_probe layer (v2 API only)."""

from django.utils import timezone
from rest_framework import serializers

from pre_consultation.layers.patient_concern_probe import (
    PatientConcernProbeConcernRequestSerializer,
    build_patient_concern_probe_payload,
    update_concern_probe_scores_for_session,
)
from pre_consultation.layers.patient_symptom import (
    PatientSymptomConcernRequestSerializer,
    PatientSymptomFamilyRelationRequestSerializer,
    PatientSymptomFamilyRelationResponseSerializer,
    PatientSymptomItemResponseSerializer,
    build_patient_symptom_payload,
    persist_concern_symptom_data,
)
from pre_consultation.models import PreConsultationSession
from pre_consultation.persistence import get_session_concern_ids
from pre_consultation.utils.constants import PreConsultationLayerProgression


class PatientConcernProbeV2ConcernRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    selected_symptom_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )
    selected_concern_source_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )
    selected_family_relations = PatientSymptomFamilyRelationRequestSerializer(
        many=True,
        allow_empty=True,
    )
    selected_functional_impact_id = serializers.CharField()
    selected_duration_impact_id = serializers.CharField()
    selected_progression_impact_id = serializers.CharField()

    def validate(self, attrs: dict) -> dict:
        symptom_serializer = PatientSymptomConcernRequestSerializer(
            data={
                "id": attrs["id"],
                "selected_symptom_ids": attrs["selected_symptom_ids"],
                "selected_concern_source_ids": attrs["selected_concern_source_ids"],
                "selected_family_relations": attrs["selected_family_relations"],
            },
            context=self.context,
        )
        symptom_serializer.is_valid(raise_exception=True)

        probe_serializer = PatientConcernProbeConcernRequestSerializer(
            data={
                "id": attrs["id"],
                "selected_functional_impact_id": attrs[
                    "selected_functional_impact_id"
                ],
                "selected_duration_impact_id": attrs["selected_duration_impact_id"],
                "selected_progression_impact_id": attrs[
                    "selected_progression_impact_id"
                ],
            },
            context=self.context,
        )
        probe_serializer.is_valid(raise_exception=True)

        return {
            **symptom_serializer.validated_data,
            "selected_functional_impact_id": probe_serializer.validated_data[
                "selected_functional_impact_id"
            ],
            "selected_duration_impact_id": probe_serializer.validated_data[
                "selected_duration_impact_id"
            ],
            "selected_progression_impact_id": probe_serializer.validated_data[
                "selected_progression_impact_id"
            ],
        }


class PatientConcernProbeV2RequestSerializer(serializers.Serializer):
    concerns = PatientConcernProbeV2ConcernRequestSerializer(many=True)


class PatientConcernProbeV2CategoryResponseSerializer(serializers.Serializer):
    label = serializers.CharField()


class PatientConcernProbeV2ConcernResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected_family_relation = PatientSymptomFamilyRelationResponseSerializer(
        many=True
    )
    selected_concern_source = serializers.ListField(child=serializers.CharField())
    symptom = PatientSymptomItemResponseSerializer(many=True)
    selected_functional_impact = serializers.CharField(allow_blank=True)
    selected_duration_impact = serializers.CharField(allow_blank=True)
    selected_progression_impact = serializers.CharField(allow_blank=True)
    category = PatientConcernProbeV2CategoryResponseSerializer()


class PatientConcernProbeV2ResponseSerializer(serializers.Serializer):
    concern_source = serializers.ListField(child=serializers.DictField())
    age_band = serializers.ListField(child=serializers.DictField())
    family_relation = serializers.ListField(child=serializers.DictField())
    functional_impact = serializers.ListField(child=serializers.DictField())
    duration_impact = serializers.ListField(child=serializers.DictField())
    progression_impact = serializers.ListField(child=serializers.DictField())
    concerns = PatientConcernProbeV2ConcernResponseSerializer(many=True)


def merge_concern_probe_v2_concerns(
    symptom_concerns: list[dict],
    probe_concerns: list[dict],
) -> list[dict]:
    probe_concern_by_id = {
        concern["id"]: concern for concern in probe_concerns
    }
    merged_concerns = []
    for symptom_concern in symptom_concerns:
        probe_concern = probe_concern_by_id[symptom_concern["id"]]
        merged_concerns.append(
            {
                **symptom_concern,
                "selected_functional_impact": probe_concern[
                    "selected_functional_impact"
                ],
                "selected_duration_impact": probe_concern["selected_duration_impact"],
                "selected_progression_impact": probe_concern[
                    "selected_progression_impact"
                ],
                "category": probe_concern["category"],
            }
        )
    return merged_concerns


def load_patient_concern_probe_v2_payload(
    user,
    session: PreConsultationSession,
) -> dict:
    symptom_payload = build_patient_symptom_payload(session)
    probe_payload = build_patient_concern_probe_payload(session)
    return {
        "concern_source": symptom_payload["concern_source"],
        "age_band": symptom_payload["age_band"],
        "family_relation": symptom_payload["family_relation"],
        "functional_impact": probe_payload["functional_impact"],
        "duration_impact": probe_payload["duration_impact"],
        "progression_impact": probe_payload["progression_impact"],
        "concerns": merge_concern_probe_v2_concerns(
            symptom_payload["concerns"],
            probe_payload["concerns"],
        ),
    }


def build_patient_concern_probe_v2_put_context(session, request) -> dict:
    return {"session_concern_ids": get_session_concern_ids(session)}


def persist_patient_concern_probe_v2_payload(
    user,
    session: PreConsultationSession,
    validated_data: dict,
) -> None:
    for concern_data in validated_data["concerns"]:
        concern = session.concerns.get(concern_id=concern_data["id"])
        persist_concern_symptom_data(concern, concern_data)
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
