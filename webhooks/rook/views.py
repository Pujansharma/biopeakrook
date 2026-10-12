from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny

from core.utils.views.main import BaseGenericAPIView
from wearables.services.ingestion import ingest_rook_document
from wearables.services.notifications import process_rook_notification
from wearables.services.signature import verify_rook_webhook_signature


def webhook_documents(payload) -> list[dict]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError("ROOK webhook payload must be an object or object array.")


class RookWebhookView(BaseGenericAPIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def validate_signature(self, payload, request) -> bool:
        if not getattr(settings, "WEARABLES_ENABLED", True):
            raise NotFound("Wearable integration is not enabled.")
        signature_header = request.headers.get("X-ROOK-HASH", "")
        signature_valid = verify_rook_webhook_signature(
            payload=payload,
            signature_header=signature_header,
        )
        if not signature_valid:
            self.raise_permission_denied("Invalid ROOK webhook signature.")
        return bool(getattr(settings, "ROOK_WEBHOOK_HASH_KEY", ""))


class RookDataWebhookView(RookWebhookView):
    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={202: OpenApiTypes.OBJECT},
    )
    def post(self, request, *args, **kwargs):
        payload = request.data
        if isinstance(payload, list) and getattr(
            settings, "ROOK_WEBHOOK_HASH_KEY", ""
        ):
            self.raise_bad_request(
                "Signed ROOK v2 data webhooks must contain one document."
            )
        signature_valid = self.validate_signature(payload, request)
        try:
            documents = webhook_documents(payload)
            results = [
                ingest_rook_document(document, signature_valid=signature_valid)
                for document in documents
            ]
        except (TypeError, ValueError) as error:
            self.raise_bad_request(str(error))
        return self.send_response(
            "ROOK webhook accepted.",
            {"results": results},
            status=202,
        )


class RookNotificationWebhookView(RookWebhookView):
    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={202: OpenApiTypes.OBJECT},
    )
    def post(self, request, *args, **kwargs):
        payload = request.data
        if not isinstance(payload, dict):
            self.raise_bad_request("ROOK notification must be an object.")
        self.validate_signature(payload, request)
        return self.send_response(
            "ROOK notification accepted.",
            process_rook_notification(payload),
            status=202,
        )

