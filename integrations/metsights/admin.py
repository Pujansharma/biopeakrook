from django.contrib import admin

from integrations.metsights.models import MetsightsProfile


@admin.register(MetsightsProfile)
class MetsightsProfileAdmin(admin.ModelAdmin):
    list_display = ['customer_profile', 'profile_id', 'created_at']
    search_fields = ['customer_profile__id', 'profile_id']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['customer_profile']

    def has_change_permission(self, request, obj=None) -> bool:
        return False
