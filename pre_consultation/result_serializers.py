"""Serializers for pre-consultation result API write endpoints."""

from rest_framework import serializers

from pre_consultation.utils.constants import PreConsultationSessionNoteCategory


class PreConsultationSessionNoteCreateSerializer(serializers.Serializer):
    note = serializers.CharField()
    category = serializers.ChoiceField(choices=PreConsultationSessionNoteCategory.choices)


class PreConsultationChecklistItemPatchSerializer(serializers.Serializer):
    done = serializers.BooleanField()


class PreConsultationSessionListItemSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    id = serializers.UUIDField()
    contact_email = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    first_name = serializers.CharField(allow_null=True)
    last_name = serializers.CharField(allow_null=True)
    gender = serializers.CharField(allow_null=True)
    date_of_birth = serializers.DateField(allow_null=True)
    height = serializers.FloatField(allow_null=True)
    weight = serializers.FloatField(allow_null=True)
    status = serializers.ChoiceField(choices=["In Progress", "Completed"])
