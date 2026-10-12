from django.contrib import admin

from wearables.models import (
    HealthDailySummary,
    HealthDomainSnapshot,
    HealthObservation,
    HealthProcessingJob,
    RookHealthDocument,
    RookMemberIdentity,
    RookWebhookReceipt,
    WearableConnection,
    WearableConnectionEvent,
    WearableConsent,
)

admin.site.register(RookMemberIdentity)
admin.site.register(WearableConsent)
admin.site.register(WearableConnection)
admin.site.register(WearableConnectionEvent)
admin.site.register(RookHealthDocument)
admin.site.register(RookWebhookReceipt)
admin.site.register(HealthObservation)
admin.site.register(HealthDailySummary)
admin.site.register(HealthDomainSnapshot)
admin.site.register(HealthProcessingJob)
