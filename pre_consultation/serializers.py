"""Serializers for session start/response payloads."""

from rest_framework import serializers

from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import PreConsultationSessionInterface


class PreConsultationSessionStartSerializer(serializers.Serializer):
    interface = serializers.ChoiceField(choices=PreConsultationSessionInterface.choices)
    app_version = serializers.CharField(max_length=50)
    locale = serializers.CharField(max_length=20)
    device = serializers.CharField(max_length=255)


class PreConsultationSessionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreConsultationSession
        fields = ["status", "current_layer"]
        read_only_fields = fields
