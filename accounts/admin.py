from django.contrib import admin

from accounts.models import UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = [
        "user__id",
        "user__email",
        "user__phone",
        "account_type",
        "created_at",
    ]
    readonly_fields = ["created_at", "updated_at"]
    list_select_related = True
    raw_id_fields = ["user"]
    list_per_page = 25
    search_fields = ["user__email", "user__phone"]
    list_filter = ["account_type"]
