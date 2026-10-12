from django.test import TestCase

from accounts.customers.models import Customer, CustomerProfile
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType
from wearables.models import HealthDailySummary, RookHealthDocument
from wearables.services.identity import get_or_create_rook_identity
from wearables.services.ingestion import ingest_rook_document, normalize_health_document


class RookIngestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="phase-one@example.com")
        UserAccount.objects.create(user=self.user, account_type=UserType.CUSTOMER)
        self.customer = Customer.objects.create(user=self.user)
        self.customer_profile = CustomerProfile.objects.create(
            customer=self.customer,
            first_name="Phase",
            last_name="One",
            is_main=True,
        )
        self.identity = get_or_create_rook_identity(self.customer_profile)

    def payload(self, *, version: int, steps: int) -> dict:
        return {
            "client_uuid": "client-one",
            "user_id": self.identity.rook_user_id,
            "datetime": "2026-10-08T10:00:00+00:00",
            "data_structure": "physical_health_summary",
            "document_version": version,
            "source_of_data_string": "Garmin",
            "accumulated_steps_int": steps,
        }

    def test_exact_replay_and_higher_version_are_idempotent(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = ingest_rook_document(self.payload(version=1, steps=5000), signature_valid=True)
        replay = ingest_rook_document(self.payload(version=1, steps=5000), signature_valid=True)
        same_version_conflict = ingest_rook_document(
            self.payload(version=1, steps=6000),
            signature_valid=True,
        )
        with self.captureOnCommitCallbacks(execute=True):
            correction = ingest_rook_document(
                self.payload(version=2, steps=7000),
                signature_valid=True,
            )

        self.assertTrue(first["queued"])
        self.assertTrue(replay["duplicate"])
        self.assertEqual(same_version_conflict["reason"], "same_version_conflict")
        self.assertEqual(correction["version"], 2)
        document = RookHealthDocument.objects.get()
        self.assertEqual(document.document_version, 2)
        self.assertEqual(document.payload["accumulated_steps_int"], 7000)

        with self.captureOnCommitCallbacks(execute=True):
            normalize_health_document(document.pk)
        summary = HealthDailySummary.objects.get(metric="steps")
        self.assertEqual(summary.maximum, 7000.0)

