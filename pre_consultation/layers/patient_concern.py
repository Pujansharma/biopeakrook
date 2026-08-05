"""Layer 3 — concern selection filtered by chosen categories."""

from rest_framework import serializers

from pre_consultation.layers.serialization import DirectiveJsonKeyCharField
from pre_consultation.models import PreConsultationConcern, PreConsultationSession
from pre_consultation.persistence import (
    get_session_category_ids,
    get_session_concern_ids,
)
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.directive import (
    get_concern_category_id_map,
    get_directive_categories,
    get_directive_concerns_for_category,
    get_valid_concern_ids,
)


class PatientConcernItemResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    selected = serializers.BooleanField()


class PatientConcernCategoryResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()
    icon_class = DirectiveJsonKeyCharField(json_key="icon-class")
    concerns = PatientConcernItemResponseSerializer(many=True)


class PatientConcernRequestSerializer(serializers.Serializer):
    concern_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )

    def validate_concern_ids(self, value: list[str]) -> list[str]:
        unique_concern_ids = list(dict.fromkeys(value))
        valid_concern_ids = get_valid_concern_ids()
        invalid_concern_ids = set(unique_concern_ids) - valid_concern_ids
        if invalid_concern_ids:
            invalid_list = ", ".join(sorted(invalid_concern_ids))
            raise serializers.ValidationError(f"Invalid concern_ids: {invalid_list}")

        selected_category_ids = self.context["selected_category_ids"]
        concern_category_id_map = get_concern_category_id_map()
        disallowed_concern_ids = [
            concern_id
            for concern_id in unique_concern_ids
            if concern_category_id_map[concern_id] not in selected_category_ids
        ]
        if disallowed_concern_ids:
            disallowed_list = ", ".join(sorted(disallowed_concern_ids))
            raise serializers.ValidationError(
                f"concern_ids require a selected category: {disallowed_list}"
            )
        return unique_concern_ids


class PatientConcernResponseSerializer(serializers.Serializer):
    categories = PatientConcernCategoryResponseSerializer(many=True)


def build_patient_concern_payload(session: PreConsultationSession) -> dict:
    selected_category_ids = get_session_category_ids(session)
    selected_concern_ids = get_session_concern_ids(session)
    categories = []
    for category in get_directive_categories():
        if category["id"] not in selected_category_ids:
            continue
        concerns = [
            {
                "id": concern["id"],
                "label": concern["label"],
                "selected": concern["id"] in selected_concern_ids,
            }
            for concern in get_directive_concerns_for_category(category["id"])
        ]
        categories.append(
            {
                "id": category["id"],
                "label": category["label"],
                "icon": category["icon"],
                "icon-class": category["icon-class"],
                "concerns": concerns,
            }
        )
    return {"categories": categories}


def load_patient_concern_payload(user, session: PreConsultationSession) -> dict:
    return build_patient_concern_payload(session)


def write_patient_concern_selection(
    session: PreConsultationSession, validated_data: dict
) -> None:
    concern_ids = validated_data["concern_ids"]
    PreConsultationConcern.objects.filter(session=session).exclude(
        concern_id__in=concern_ids,
    ).delete()

    existing_concern_ids = get_session_concern_ids(session)
    new_concern_ids = [
        concern_id
        for concern_id in concern_ids
        if concern_id not in existing_concern_ids
    ]
    PreConsultationConcern.objects.bulk_create(
        [
            PreConsultationConcern(session=session, concern_id=concern_id)
            for concern_id in new_concern_ids
        ]
    )


def persist_patient_concern_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    write_patient_concern_selection(session, validated_data)
    session.current_layer = PreConsultationLayerProgression.PATIENT_SYMPTOM
    session.save(update_fields=["current_layer", "updated_at"])


def persist_patient_concern_v2_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    write_patient_concern_selection(session, validated_data)
    session.current_layer = PreConsultationLayerProgression.PATIENT_CONCERN_PROBE
    session.save(update_fields=["current_layer", "updated_at"])


def build_patient_concern_put_context(session, request) -> dict:
    return {"selected_category_ids": get_session_category_ids(session)}
