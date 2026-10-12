from django.contrib import admin

from integrations.models import (
    AppDownloadClick,
    CommunicationOutbox,
    CommunicationWebhookEvent,
)


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


@admin.register(AppDownloadClick)
class AppDownloadClickAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "platform",
        "entry",
        "source",
        "campaign",
        "ip_address",
        "created_at",
    )
    list_filter = ("platform", "entry", "source")
    search_fields = ("source", "campaign", "user_agent", "destination_url")
    readonly_fields = (
        "id",
        "platform",
        "entry",
        "destination_url",
        "user_agent",
        "ip_address",
        "source",
        "campaign",
        "referer",
        "is_active",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
