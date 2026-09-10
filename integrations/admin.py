from django.contrib import admin

from integrations.models import CommunicationOutbox, CommunicationWebhookEvent


@admin.register(CommunicationOutbox)
class CommunicationOutboxAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "appointment",
        "event_type",
        "channel",
        "status",
        "to_phone",
        "wamid",
        "created_at",
    )
    list_filter = ("channel", "event_type", "status")
    search_fields = ("to_phone", "wamid", "template_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CommunicationWebhookEvent)
class CommunicationWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_key", "wamid", "status", "created_at")
    search_fields = ("event_key", "wamid")
    readonly_fields = ("created_at", "updated_at")
