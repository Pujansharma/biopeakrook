"""Serializers for pre-consultation result API write endpoints."""

from rest_framework import serializers

from pre_consultation.utils.constants import PreConsultationSessionNoteCategory


class PreConsultationSessionNoteCreateSerializer(serializers.Serializer):
    note = serializers.CharField()
    category = serializers.ChoiceField(choices=PreConsultationSessionNoteCategory.choices)


class PreConsultationChecklistItemPatchSerializer(serializers.Serializer):
    done = serializers.BooleanField()
