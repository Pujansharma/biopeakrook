from rest_framework import serializers

from appointments.serializers.booking import AppointmentListSerializer
from core.utils.serializers import BaseSerializer


class AppointmentExceptionSourceSerializer(BaseSerializer):
    source_type = serializers.CharField()
    source_id = serializers.UUIDField()
    source_label = serializers.CharField()
    source_start = serializers.DateTimeField(source="source_start_datetime")
    source_end = serializers.DateTimeField(source="source_end_datetime")


class AppointmentExceptionListSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    status = serializers.CharField()
    resolution = serializers.CharField(allow_null=True)
    detected_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)
    appointment = AppointmentListSerializer()
    source = serializers.SerializerMethodField()

    def get_source(self, obj):
        return AppointmentExceptionSourceSerializer(obj).data


class AppointmentExceptionCountSerializer(BaseSerializer):
    open_count = serializers.IntegerField()
