from django.contrib import admin

from webhooks.strand_genomics.models import StrandGenomicsWebhook


@admin.register(StrandGenomicsWebhook)
class StrandGenomicsWebhookAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "data", "created_at", "updated_at"]
    list_display = ["id", "created_at"]
    list_per_page = 25

    def has_change_permission(self, request, obj=...):
        return False

    def has_add_permission(self, request):
        return False
