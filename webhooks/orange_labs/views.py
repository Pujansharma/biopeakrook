from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from core.utils.serializers import BaseSerializer
from core.utils.views.main import BaseCreateAPIView
from diagnostics_orders.models import DiagnosticOrder, DiagnosticOrderEvent
from diagnostics_orders.utils.constants import DiagnosticOrderStatus
from diagnostics_orders.utils.db import bump_summary_completed
from webhooks.orange_labs.utils.payload import (
    REPORT_EVENTS,
    extract_city_request_id,
    extract_event_type,
    extract_raw_reports,
    merge_reports_by_id,
)
from webhooks.orange_labs.utils.signature import verify_orange_webhook_signature


class OrangeLabsWebhookSerializer(BaseSerializer):
    payload = serializers.JSONField(required=False, write_only=True)

    @transaction.atomic
    def create(self, validated_data):
        body = validated_data.get("payload") or {}
        if not isinstance(body, dict):
            return True

        orange_event_id = self.context.get("orange_event_id")
        if orange_event_id and DiagnosticOrderEvent.objects.filter(
            orange_event_id=orange_event_id
        ).exists():
            return True

        event_type = extract_event_type(body)
        city_request_id = extract_city_request_id(body)
        if not city_request_id:
            return True

        order = DiagnosticOrder.objects.filter(request_id=city_request_id).first()
        if not order:
            return True

        DiagnosticOrderEvent.objects.create(
            order=order,
            event_type=event_type,
            payload=body,
            orange_event_id=orange_event_id or None,
        )

        update_fields = []
        status_value = event_type
        valid_statuses = {choice.value for choice in DiagnosticOrderStatus}
        previous_status = order.status
        if status_value in valid_statuses and order.status != status_value:
            order.status = status_value
            update_fields.append("status")

        if event_type in REPORT_EVENTS:
            merged_reports = merge_reports_by_id(
                order.reports,
                extract_raw_reports(body),
            )
            if merged_reports != (order.reports or []):
                order.reports = merged_reports
                update_fields.append("reports")

        if update_fields:
            update_fields.append("updated_at")
            order.save(update_fields=update_fields)
            if (
                "status" in update_fields
                and order.status == DiagnosticOrderStatus.ORDER_COMPLETED
                and previous_status != DiagnosticOrderStatus.ORDER_COMPLETED
            ):
                bump_summary_completed()

        return True


class OrangeLabsWebhookView(BaseCreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = OrangeLabsWebhookSerializer

    def post(self, request, *args, **kwargs):
        secret = getattr(settings, "ORANGE_LABS_WEBHOOK_SECRET", None) or ""
        signature_header = request.headers.get("X-OH-Signature", "")
        if not verify_orange_webhook_signature(
            body=request.body,
            signature_header=signature_header,
            secret=secret,
        ):
            self.raise_permission_denied("Invalid Biopeak Health webhook signature")

        orange_event_id = request.headers.get("X-OH-Event-Id") or None
        serializer = self.get_serializer(
            data={"payload": request.data},
            context={
                **self.get_serializer_context(),
                "orange_event_id": orange_event_id,
            },
        )
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.send_response("Webhook received successfully")
