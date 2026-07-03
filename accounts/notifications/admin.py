from django.contrib import admin

from accounts.notifications.models import FirebaseRegistrationToken


@admin.register(FirebaseRegistrationToken)
class FirebaseRegistrationTokenAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "get_token", "created_at", "updated_at"]
    list_display = ["id", "user_id", "created_at", "is_active"]
    list_per_page = 25
    exclude = ['token']
    list_filter = ["is_active"]

    @admin.display(description="Token")
    def get_token(self, instance: FirebaseRegistrationToken):
        if instance.token:
            return instance.token[:4] + "*****" + instance.token[-4:]
        return None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
