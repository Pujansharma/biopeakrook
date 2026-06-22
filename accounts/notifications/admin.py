from django.contrib import admin

from accounts.notifications.models import FirebaseRegistrationToken


@admin.register(FirebaseRegistrationToken)
class FirebaseRegistrationTokenAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "user_id", "created_at", "is_active"]
    list_per_page = 25
    list_filter = ["is_active"]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
