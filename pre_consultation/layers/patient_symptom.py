"""Layer 4 — symptoms, sources, and family history per selected concern."""

from rest_framework import serializers

from pre_consultation.models import (
    PreConsultationConcern,
    PreConsultationConcernFamilyHistory,
    PreConsultationConcernSource,
    PreConsultationConcernSymptom,
    PreConsultationSession,
)
from pre_consultation.persistence import (
    get_session_concern_ids,
    get_session_concerns_ordered,
)
from pre_consultation.utils.constants import (
    PreConsultationConcernSourceId,
    PreConsultationLayerProgression,
)
from pre_consultation.utils.directive import (
    get_directive_age_bands,
    get_directive_concern_label_map,
    get_directive_concern_sources,
    get_directive_family_relations,
    get_directive_symptoms_for_concern,
    get_valid_age_band_ids,
    get_valid_concern_source_ids,
    get_valid_family_relation_ids,
    get_valid_symptom_ids_for_concern,
)


class PatientSymptomFamilyRelationRequestSerializer(serializers.Serializer):
    id = serializers.CharField(allow_blank=False)
    age_band_id = serializers.CharField(allow_blank=False)


def validate_selected_symptoms_require_lab_result_source(
    selected_symptom_ids: list[str],
    selected_concern_source_ids: list[str],
) -> dict[str, list[str]] | None:
    if (
        selected_symptom_ids
        and PreConsultationConcernSourceId.LAB_RESULT not in selected_concern_source_ids
    ):
        return {
            "selected_symptom_ids": [
                "Can only be set when selected_concern_source_ids includes lab_result."
            ]
        }
    return None


def validate_lab_result_source_requires_symptoms(
    selected_symptom_ids: list[str],
    selected_concern_source_ids: list[str],
) -> dict[str, list[str]] | None:
    if (
        PreConsultationConcernSourceId.LAB_RESULT in selected_concern_source_ids
        and not selected_symptom_ids
    ):
        return {
            "selected_symptom_ids": [
                "Required when selected_concern_source_ids includes lab_result."
            ]
        }
    return None


def validate_selected_family_relations_require_family_source(
    selected_family_relations: list[dict],
    selected_concern_source_ids: list[str],
) -> dict[str, list[str]] | None:
    if (
        selected_family_relations
        and PreConsultationConcernSourceId.FAMILY not in selected_concern_source_ids
    ):
        return {
            "selected_family_relations": [
                "Can only be set when selected_concern_source_ids includes family."
            ]
        }
    return None


def validate_family_source_requires_family_relations(
    selected_family_relations: list[dict],
    selected_concern_source_ids: list[str],
) -> dict[str, list[str]] | None:
    if (
        PreConsultationConcernSourceId.FAMILY in selected_concern_source_ids
        and not selected_family_relations
    ):
        return {
            "selected_family_relations": [
                "Required when selected_concern_source_ids includes family."
            ]
        }
    return None


def validate_selected_family_relations_exist(
    selected_family_relations: list[dict],
    valid_family_relation_ids: set[str],
    valid_age_band_ids: set[str],
) -> dict[str, list[str]] | None:
    for family_relation in selected_family_relations:
        relation_id = family_relation.get("id")
        age_band_id = family_relation.get("age_band_id")
        if not relation_id:
            return {"selected_family_relations": ["Each entry requires id."]}
        if not age_band_id:
            return {"selected_family_relations": ["Each entry requires age_band_id."]}
        if relation_id not in valid_family_relation_ids:
            return {
                "selected_family_relations": [f"Invalid relation id: {relation_id}"]
            }
        if age_band_id not in valid_age_band_ids:
            return {
                "selected_family_relations": [f"Invalid age_band_id: {age_band_id}"]
            }
    return None


class PatientSymptomConcernRequestSerializer(serializers.Serializer):
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

    def validate_id(self, value: str) -> str:
        session_concern_ids = self.context["session_concern_ids"]
        if value not in session_concern_ids:
            raise serializers.ValidationError(
                "Concern is not selected for this session."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        concern_id = attrs["id"]
        symptom_ids = list(dict.fromkeys(attrs["selected_symptom_ids"]))
        valid_symptom_ids = get_valid_symptom_ids_for_concern(concern_id)
        invalid_symptom_ids = set(symptom_ids) - valid_symptom_ids
        if invalid_symptom_ids:
            invalid_list = ", ".join(sorted(invalid_symptom_ids))
            raise serializers.ValidationError(
                {"selected_symptom_ids": f"Invalid ids: {invalid_list}"}
            )

        concern_source_ids = list(dict.fromkeys(attrs["selected_concern_source_ids"]))
        valid_concern_source_ids = get_valid_concern_source_ids()
        invalid_concern_source_ids = set(concern_source_ids) - valid_concern_source_ids
        if invalid_concern_source_ids:
            invalid_list = ", ".join(sorted(invalid_concern_source_ids))
            raise serializers.ValidationError(
                {"selected_concern_source_ids": f"Invalid ids: {invalid_list}"}
            )

        symptom_source_error = validate_selected_symptoms_require_lab_result_source(
            symptom_ids,
            concern_source_ids,
        )
        if symptom_source_error:
            raise serializers.ValidationError(symptom_source_error)

        symptoms_required_error = validate_lab_result_source_requires_symptoms(
            symptom_ids,
            concern_source_ids,
        )
        if symptoms_required_error:
            raise serializers.ValidationError(symptoms_required_error)

        family_source_error = validate_selected_family_relations_require_family_source(
            attrs["selected_family_relations"],
            concern_source_ids,
        )
        if family_source_error:
            raise serializers.ValidationError(family_source_error)

        family_relations_required_error = (
            validate_family_source_requires_family_relations(
                attrs["selected_family_relations"],
                concern_source_ids,
            )
        )
        if family_relations_required_error:
            raise serializers.ValidationError(family_relations_required_error)

        valid_age_band_ids = get_valid_age_band_ids()
        valid_family_relation_ids = get_valid_family_relation_ids()
        family_relations_error = validate_selected_family_relations_exist(
            attrs["selected_family_relations"],
            valid_family_relation_ids,
            valid_age_band_ids,
        )
        if family_relations_error:
            raise serializers.ValidationError(family_relations_error)

        attrs["selected_symptom_ids"] = symptom_ids
        attrs["selected_concern_source_ids"] = concern_source_ids
        return attrs


class PatientSymptomRequestSerializer(serializers.Serializer):
    concerns = PatientSymptomConcernRequestSerializer(many=True)


class PatientSymptomFamilyRelationResponseSerializer(serializers.Serializer):
    relation_id = serializers.CharField()
    age_band_id = serializers.CharField()


class PatientSymptomItemResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected = serializers.BooleanField()


class PatientSymptomSelectedConcernResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected_family_relation = PatientSymptomFamilyRelationResponseSerializer(many=True)
    selected_concern_source = serializers.ListField(child=serializers.CharField())
    symptom = PatientSymptomItemResponseSerializer(many=True)


class PatientSymptomResponseSerializer(serializers.Serializer):
    concern_source = serializers.ListField(child=serializers.DictField())
    age_band = serializers.ListField(child=serializers.DictField())
    family_relation = serializers.ListField(child=serializers.DictField())
    concerns = PatientSymptomSelectedConcernResponseSerializer(many=True)


def build_concern_symptom_payload(concern: PreConsultationConcern) -> dict:
    selected_symptom_ids = set(concern.symptoms.values_list("symptom_id", flat=True))
    selected_concern_source_ids = list(
        concern.sources.values_list("source_id", flat=True)
    )
    selected_family_relations = [
        {
            "relation_id": family_history.relation_id,
            "age_band_id": family_history.age_band_id,
        }
        for family_history in concern.family_history.order_by("created_at")
    ]
    concern_label_map = get_directive_concern_label_map()
    symptoms = [
        {
            "id": symptom["id"],
            "label": symptom["label"],
            "selected": symptom["id"] in selected_symptom_ids,
        }
        for symptom in get_directive_symptoms_for_concern(concern.concern_id)
    ]
    return {
        "id": concern.concern_id,
        "label": concern_label_map[concern.concern_id],
        "selected_family_relation": selected_family_relations,
        "selected_concern_source": selected_concern_source_ids,
        "symptom": symptoms,
    }


def build_patient_symptom_payload(session: PreConsultationSession) -> dict:
    concerns = [
        build_concern_symptom_payload(concern)
        for concern in get_session_concerns_ordered(session)
    ]
    return {
        "concern_source": get_directive_concern_sources(),
        "age_band": get_directive_age_bands(),
        "family_relation": get_directive_family_relations(),
        "concerns": concerns,
    }


def load_patient_symptom_payload(user, session: PreConsultationSession) -> dict:
    return build_patient_symptom_payload(session)


def build_patient_symptom_put_context(session, request) -> dict:
    return {"session_concern_ids": get_session_concern_ids(session)}


def persist_concern_symptom_data(
    concern: PreConsultationConcern,
    concern_data: dict,
) -> None:
    symptom_ids = concern_data["selected_symptom_ids"]
    concern_source_ids = concern_data["selected_concern_source_ids"]
    family_relations = concern_data["selected_family_relations"]

    concern.symptoms.exclude(symptom_id__in=symptom_ids).delete()
    existing_symptom_ids = set(concern.symptoms.values_list("symptom_id", flat=True))
    PreConsultationConcernSymptom.objects.bulk_create(
        [
            PreConsultationConcernSymptom(concern=concern, symptom_id=symptom_id)
            for symptom_id in symptom_ids
            if symptom_id not in existing_symptom_ids
        ]
    )

    concern.sources.exclude(source_id__in=concern_source_ids).delete()
    existing_source_ids = set(concern.sources.values_list("source_id", flat=True))
    PreConsultationConcernSource.objects.bulk_create(
        [
            PreConsultationConcernSource(concern=concern, source_id=source_id)
            for source_id in concern_source_ids
            if source_id not in existing_source_ids
        ]
    )

    concern.family_history.all().delete()
    PreConsultationConcernFamilyHistory.objects.bulk_create(
        [
            PreConsultationConcernFamilyHistory(
                concern=concern,
                relation_id=family_relation["id"],
                age_band_id=family_relation["age_band_id"],
            )
            for family_relation in family_relations
        ]
    )


def persist_patient_symptom_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    for concern_data in validated_data["concerns"]:
        concern = session.concerns.get(concern_id=concern_data["id"])
        persist_concern_symptom_data(concern, concern_data)

    session.current_layer = PreConsultationLayerProgression.PATIENT_CONCERN_PROBE
    session.save(update_fields=["current_layer", "updated_at"])
