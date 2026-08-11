from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from core.utils.serializers import BaseSerializer
from core.utils.views.main import BaseCreateAPIView
from diagnostics_orders.models import DiagnosticOrder, DiagnosticOrderEvent
from diagnostics_orders.utils.constants import DiagnosticOrderStatus
from diagnostics_orders.utils.db import bump_summary_completed


class OrangeLabsWebhookSerializer(BaseSerializer):
    payload = serializers.JSONField(required=False, write_only=True)

    @transaction.atomic
    def create(self, validated_data):
        payload = validated_data.get("payload") or {}
        if not isinstance(payload, dict):
            return True

        request_id = (
            payload.get("request_id")
            or (payload.get("data") or {}).get("request_id")
        )
        event_type = (
            payload.get("event_type")
            or payload.get("event")
            or payload.get("status")
            or "unknown"
        )
        orange_event_id = payload.get("event_id") or payload.get("id")

        if orange_event_id and DiagnosticOrderEvent.objects.filter(
            orange_event_id=orange_event_id
        ).exists():
            return True

        order = None
        if request_id:
            order = DiagnosticOrder.objects.filter(request_id=request_id).first()

        if order:
            DiagnosticOrderEvent.objects.create(
                order=order,
                event_type=str(event_type),
                payload=payload,
                orange_event_id=orange_event_id,
            )
            status_value = str(event_type)
            valid_statuses = {choice.value for choice in DiagnosticOrderStatus}
            if status_value in valid_statuses and order.status != status_value:
                previous_status = order.status
                order.status = status_value
                order.save(update_fields=["status", "updated_at"])
                if (
                    status_value == DiagnosticOrderStatus.ORDER_COMPLETED
                    and previous_status != DiagnosticOrderStatus.ORDER_COMPLETED
                ):
                    bump_summary_completed()
        return True


class OrangeLabsWebhookView(BaseCreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = OrangeLabsWebhookSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data={"payload": request.data})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.send_response("Webhook received successfully")
