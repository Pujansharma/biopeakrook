from rest_framework import serializers

from core.utils.serializers import BaseSerializer


class MetsightsWebhookSerializer(BaseSerializer):
    payload = serializers.JSONField(required=False, write_only=True)

    def create(self, validated_data):
        payload = validated_data.get('payload') or {}
        scope = payload.get('scope')
        data = payload.get('data')
        print("DATA: ", payload)
        email = payload.get('email')
        return True
