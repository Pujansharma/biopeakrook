from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from rest_framework import serializers

from core.utils.serializers import BaseSerializer
from wearables.utils.constants import (
    HEALTH_DOMAIN_ORDER,
    NATIVE_WEARABLE_SOURCES,
    PermissionStatus,
    PreferredUnits,
    WearableSource,
)


class DeviceConnectSerializer(BaseSerializer):
    data_source = serializers.ChoiceField(choices=WearableSource.choices)
    consent_accepted = serializers.BooleanField(write_only=True)
    consent_version = serializers.CharField(max_length=32, default="v1")
    historical_days = serializers.IntegerField(
        min_value=0,
        max_value=180,
        default=settings.ROOK_HISTORICAL_DAYS,
    )
    redirect_url = serializers.URLField(required=False, allow_blank=False)
    timezone_name = serializers.CharField(max_length=64, required=False)
    preferred_units = serializers.ChoiceField(
        choices=PreferredUnits.choices,
        required=False,
    )

    def validate_consent_accepted(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Wearable ingestion and longitudinal storage consent is required."
            )
        return value

    def validate_timezone_name(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise serializers.ValidationError("Unknown timezone.") from error
        return value


class DeviceDisconnectSerializer(BaseSerializer):
    data_source = serializers.ChoiceField(choices=WearableSource.choices)


class NativeDeviceStatusSerializer(BaseSerializer):
    data_source = serializers.ChoiceField(
        choices=[(source, source) for source in sorted(NATIVE_WEARABLE_SOURCES)]
    )
    sdk_linked = serializers.BooleanField()
    permission_status = serializers.ChoiceField(choices=PermissionStatus.choices)
    capabilities = serializers.ListField(
        child=serializers.ChoiceField(choices=[(domain, domain) for domain in HEALTH_DOMAIN_ORDER]),
        required=False,
        allow_empty=True,
    )
    timezone_name = serializers.CharField(max_length=64, required=False)
    historical_days = serializers.IntegerField(
        min_value=0,
        max_value=180,
        required=False,
    )

    def validate_timezone_name(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise serializers.ValidationError("Unknown timezone.") from error
        return value


class DomainQuerySerializer(BaseSerializer):
    days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class TimelineQuerySerializer(BaseSerializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    domain = serializers.ChoiceField(
        choices=[(domain, domain) for domain in HEALTH_DOMAIN_ORDER],
        required=False,
    )
    offset = serializers.IntegerField(min_value=0, default=0)
    limit = serializers.IntegerField(min_value=1, max_value=200, default=50)

    def validate(self, attributes):
        start = attributes.get("start")
        end = attributes.get("end")
        if start and end and end < start:
            raise serializers.ValidationError("End date must be on or after start date.")
        return attributes

