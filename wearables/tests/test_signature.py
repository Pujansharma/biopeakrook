import hashlib
import hmac

from django.test import SimpleTestCase, override_settings

from wearables.services.signature import verify_rook_webhook_signature


class RookSignatureTests(SimpleTestCase):
    @override_settings(
        ROOK_WEBHOOK_HASH_KEY="phase-one-hash-key",
        ROOK_ALLOW_UNSIGNED_WEBHOOKS=False,
    )
    def test_accepts_document_hmac(self):
        payload = {
            "client_uuid": "client-one",
            "user_id": "member-one",
            "datetime": "2026-10-08T10:00:00Z",
        }
        message = "client-onemember-one2026-10-08T10:00:00Z"
        signature = hmac.new(
            b"phase-one-hash-key",
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(
            verify_rook_webhook_signature(
                payload=payload,
                signature_header=signature,
            )
        )

    @override_settings(
        ROOK_WEBHOOK_HASH_KEY="phase-one-hash-key",
        ROOK_ALLOW_UNSIGNED_WEBHOOKS=False,
    )
    def test_rejects_invalid_signature(self):
        self.assertFalse(
            verify_rook_webhook_signature(
                payload={
                    "client_uuid": "client-one",
                    "user_id": "member-one",
                    "datetime": "2026-10-08T10:00:00Z",
                },
                signature_header="invalid",
            )
        )

    @override_settings(
        ROOK_WEBHOOK_HASH_KEY="phase-one-hash-key",
        ROOK_ALLOW_UNSIGNED_WEBHOOKS=False,
    )
    def test_rejects_signature_when_required_fields_are_missing(self):
        signature = hmac.new(
            b"phase-one-hash-key",
            b"member-one",
            hashlib.sha256,
        ).hexdigest()

        self.assertFalse(
            verify_rook_webhook_signature(
                payload={"user_id": "member-one"},
                signature_header=signature,
            )
        )

    @override_settings(ROOK_WEBHOOK_HASH_KEY="", ROOK_ALLOW_UNSIGNED_WEBHOOKS=True)
    def test_allows_unsigned_payload_only_when_explicitly_enabled(self):
        self.assertTrue(
            verify_rook_webhook_signature(payload={"user_id": "one"}, signature_header="")
        )

