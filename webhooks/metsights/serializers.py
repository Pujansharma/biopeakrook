from rest_framework import serializers

from core.utils.serializers import BaseSerializer
from webhooks.metsights.utils.tasks import send_reports_export_email

REPORTS_EXPORT_SCOPE = "reports.export"


class MetsightsWebhookSerializer(BaseSerializer):
    payload = serializers.JSONField(required=False, write_only=True)

    def create(self, validated_data: dict) -> bool:
        payload = validated_data.get("payload") or {}
        if not isinstance(payload, dict):
            return True
        scope = payload.get("scope")
        data = payload.get("data", {}) or {}
        if not isinstance(data, dict):
            return True
        if scope == REPORTS_EXPORT_SCOPE:
            profile = data.get("profile", {}) or {}
            first_name = profile.get("first_name", "")
            files = data.get("files", [])
            send_reports_export_email(data.get("email"), first_name, files)
        return True
