"""Layer 2 — wellness category multi-select from directive catalog."""

from rest_framework import serializers

from pre_consultation.layers.reset import delete_concerns_for_deselected_categories
from pre_consultation.layers.serialization import DirectiveJsonKeyCharField
from pre_consultation.models import (
    PreConsultationCategorySelection,
    PreConsultationSession,
)
from pre_consultation.persistence import get_session_category_ids
from pre_consultation.utils.constants import PreConsultationLayerProgression
from pre_consultation.utils.directive import (
    get_directive_categories,
    get_valid_category_ids,
)


class PatientCategoryItemResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    hint = serializers.CharField()
    icon = serializers.CharField()
    icon_class = DirectiveJsonKeyCharField(json_key="icon-class")
    selected = serializers.BooleanField()


class PatientCategoryRequestSerializer(serializers.Serializer):
    category_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )

    def validate_category_ids(self, value: list[str]) -> list[str]:
        unique_category_ids = list(dict.fromkeys(value))
        valid_category_ids = get_valid_category_ids()
        invalid_category_ids = set(unique_category_ids) - valid_category_ids
        if invalid_category_ids:
            invalid_list = ", ".join(sorted(invalid_category_ids))
            raise serializers.ValidationError(f"Invalid category_ids: {invalid_list}")
        return unique_category_ids


class PatientCategoryResponseSerializer(serializers.Serializer):
    categories = PatientCategoryItemResponseSerializer(many=True)


def build_patient_category_payload(session: PreConsultationSession) -> dict:
    selected_category_ids = get_session_category_ids(session)
    categories = [
        {
            "id": category["id"],
            "label": category["label"],
            "hint": category["hint"],
            "icon": category["icon"],
            "icon-class": category["icon-class"],
            "selected": category["id"] in selected_category_ids,
        }
        for category in get_directive_categories()
    ]
    return {"categories": categories}


def load_patient_category_payload(user, session: PreConsultationSession) -> dict:
    return build_patient_category_payload(session)


def persist_patient_category_payload(
    user, session: PreConsultationSession, validated_data: dict
) -> None:
    category_ids = validated_data["category_ids"]
    PreConsultationCategorySelection.objects.filter(session=session).exclude(
        category_id__in=category_ids,
    ).delete()

    existing_category_ids = get_session_category_ids(session)
    new_category_ids = [
        category_id
        for category_id in category_ids
        if category_id not in existing_category_ids
    ]
    PreConsultationCategorySelection.objects.bulk_create(
        [
            PreConsultationCategorySelection(session=session, category_id=category_id)
            for category_id in new_category_ids
        ]
    )

    delete_concerns_for_deselected_categories(session, category_ids)

    session.current_layer = PreConsultationLayerProgression.PATIENT_CONCERN
    session.save(update_fields=["current_layer", "updated_at"])
