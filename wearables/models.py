# ruff: noqa: RUF012

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from accounts.customers.models import CustomerProfile
from core.utils.models import BaseUUIDModel
from wearables.utils.constants import (
    ALGORITHM_VERSION,
    AuthorizationStatus,
    ConfidenceLevel,
    ConnectionMethod,
    ConnectionStatus,
    ConsentStatus,
    DocumentStatus,
    HealthDomain,
    HealthJobStatus,
    HealthJobType,
    HistoricalImportStatus,
    PermissionStatus,
    PreferredUnits,
    WearableSource,
)


class RookMemberIdentity(BaseUUIDModel):
    customer_profile = models.OneToOneField(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="rook_identity",
    )
    rook_user_id = models.CharField(max_length=50, unique=True)
    timezone_name = models.CharField(max_length=64, default=settings.TIME_ZONE)
    preferred_units = models.CharField(
        max_length=16,
        choices=PreferredUnits,
        default=PreferredUnits.METRIC,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.rook_user_id


class WearableConsent(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="wearable_consents",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wearable_consents_granted",
    )
    status = models.CharField(
        max_length=16,
        choices=ConsentStatus,
        default=ConsentStatus.GRANTED,
    )
    version = models.CharField(max_length=32)
    purpose = models.CharField(
        max_length=255,
        default="Wearable ingestion and longitudinal health storage",
    )
    granted_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["-granted_at"]
        indexes = [
            models.Index(fields=["customer_profile", "status", "granted_at"]),
        ]

    def __str__(self):
        return f"{self.customer_profile_id}:{self.version}:{self.status}"


class WearableConnection(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="wearable_connections",
    )
    identity = models.ForeignKey(
        RookMemberIdentity,
        on_delete=models.CASCADE,
        related_name="connections",
    )
    data_source = models.CharField(max_length=32, choices=WearableSource)
    connection_method = models.CharField(max_length=8, choices=ConnectionMethod)
    status = models.CharField(
        max_length=32,
        choices=ConnectionStatus,
        default=ConnectionStatus.NEVER_CONNECTED,
    )
    authorization_status = models.CharField(
        max_length=24,
        choices=AuthorizationStatus,
        default=AuthorizationStatus.NOT_STARTED,
    )
    permission_status = models.CharField(
        max_length=24,
        choices=PermissionStatus,
        default=PermissionStatus.UNKNOWN,
    )
    import_status = models.CharField(
        max_length=24,
        choices=HistoricalImportStatus,
        default=HistoricalImportStatus.NOT_STARTED,
    )
    capabilities = models.JSONField(default=list, blank=True)
    historical_days_requested = models.PositiveSmallIntegerField(default=29)
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync = models.DateTimeField(null=True, blank=True)
    last_webhook_received_at = models.DateTimeField(null=True, blank=True)
    import_started_at = models.DateTimeField(null=True, blank=True)
    import_completed_at = models.DateTimeField(null=True, blank=True)
    available_from = models.DateTimeField(null=True, blank=True)
    available_to = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_detail = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["data_source"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile", "data_source"],
                name="uniq_profile_wearable_source",
            ),
        ]
        indexes = [
            models.Index(fields=["customer_profile", "status"]),
            models.Index(fields=["identity", "data_source"]),
        ]

    def __str__(self):
        return f"{self.customer_profile_id}:{self.data_source}"


class WearableConnectionEvent(BaseUUIDModel):
    connection = models.ForeignKey(
        WearableConnection,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=64)
    previous_status = models.CharField(max_length=32, blank=True)
    current_status = models.CharField(max_length=32)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wearable_connection_events",
    )
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    detail = models.CharField(max_length=512, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["connection", "created_at"])]

    def __str__(self):
        return f"{self.connection_id}:{self.event_type}"


class RookHealthDocument(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="rook_health_documents",
    )
    identity = models.ForeignKey(
        RookMemberIdentity,
        on_delete=models.CASCADE,
        related_name="health_documents",
    )
    document_identity = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64)
    data_structure = models.CharField(max_length=128, db_index=True)
    document_version = models.PositiveIntegerField(default=1)
    observed_at = models.DateTimeField(db_index=True)
    source_key = models.CharField(max_length=64, blank=True, db_index=True)
    data_sources = models.JSONField(default=list, blank=True)
    source_label = models.CharField(max_length=255, blank=True)
    device_metadata = models.JSONField(default=list, blank=True)
    source_contexts = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=DocumentStatus,
        default=DocumentStatus.RECEIVED,
    )
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_detail = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["customer_profile", "observed_at"]),
            models.Index(
                fields=["customer_profile", "data_structure", "observed_at"],
                name="wear_doc_prof_struct_time",
            ),
            models.Index(fields=["status", "received_at"]),
        ]

    def __str__(self):
        return self.document_identity


class RookWebhookReceipt(BaseUUIDModel):
    receipt_key = models.CharField(max_length=64, unique=True)
    rook_user_id = models.CharField(max_length=50, blank=True, db_index=True)
    document = models.ForeignKey(
        RookHealthDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receipts",
    )
    signature_valid = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=DocumentStatus,
        default=DocumentStatus.RECEIVED,
    )
    reason = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField()

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["status", "received_at"])]

    def __str__(self):
        return self.receipt_key


class HealthObservation(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="health_observations",
    )
    document = models.ForeignKey(
        RookHealthDocument,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    connection = models.ForeignKey(
        WearableConnection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observations",
    )
    observation_identity = models.CharField(max_length=64, unique=True)
    domain = models.CharField(max_length=16, choices=HealthDomain, db_index=True)
    metric = models.CharField(max_length=128, db_index=True)
    field_path = models.CharField(max_length=512)
    observed_at = models.DateTimeField(db_index=True)
    local_date = models.DateField(db_index=True)
    numeric_value = models.FloatField(null=True, blank=True)
    text_value = models.CharField(max_length=512, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    source_key = models.CharField(max_length=64, blank=True, db_index=True)
    data_sources = models.JSONField(default=list, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(default=1.0)
    document_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [
            models.Index(
                fields=["customer_profile", "domain", "observed_at"],
                name="wear_obs_prof_domain_time",
            ),
            models.Index(
                fields=["customer_profile", "metric", "local_date"],
                name="wear_obs_prof_metric_day",
            ),
        ]

    def __str__(self):
        return self.observation_identity


class HealthDailySummary(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="health_daily_summaries",
    )
    domain = models.CharField(max_length=16, choices=HealthDomain)
    metric = models.CharField(max_length=128)
    local_date = models.DateField()
    source_key = models.CharField(max_length=64, blank=True)
    count = models.PositiveIntegerField(default=0)
    minimum = models.FloatField(null=True, blank=True)
    maximum = models.FloatField(null=True, blank=True)
    average = models.FloatField(null=True, blank=True)
    total = models.FloatField(null=True, blank=True)
    latest = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    completeness = models.FloatField(default=0.0)
    first_observed_at = models.DateTimeField(null=True, blank=True)
    last_observed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-local_date"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "customer_profile",
                    "domain",
                    "metric",
                    "local_date",
                    "source_key",
                ],
                name="uniq_health_daily_metric_source",
            ),
        ]
        indexes = [
            models.Index(
                fields=["customer_profile", "domain", "local_date"],
                name="wear_daily_prof_domain_day",
            ),
        ]

    def __str__(self):
        return f"{self.customer_profile_id}:{self.metric}:{self.local_date}"


class HealthDomainSnapshot(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="health_domain_snapshots",
    )
    domain = models.CharField(max_length=16, choices=HealthDomain)
    state = models.CharField(max_length=32)
    card = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    algorithm_version = models.CharField(max_length=32, default=ALGORITHM_VERSION)
    confidence = models.CharField(
        max_length=16,
        choices=ConfidenceLevel,
        default=ConfidenceLevel.UNKNOWN,
    )
    generated_at = models.DateTimeField()

    class Meta:
        ordering = ["domain"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer_profile", "domain"],
                name="uniq_profile_health_domain_snapshot",
            ),
        ]

    def __str__(self):
        return f"{self.customer_profile_id}:{self.domain}"


class HealthProcessingJob(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        CustomerProfile,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="health_processing_jobs",
    )
    document = models.ForeignKey(
        RookHealthDocument,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="processing_jobs",
    )
    connection = models.ForeignKey(
        WearableConnection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="processing_jobs",
    )
    job_type = models.CharField(max_length=32, choices=HealthJobType)
    status = models.CharField(
        max_length=16,
        choices=HealthJobStatus,
        default=HealthJobStatus.PENDING,
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    failure_detail = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["scheduled_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"])]

    def __str__(self):
        return f"{self.job_type}:{self.status}:{self.idempotency_key}"
