from django.contrib import admin

from .models import Associate


@admin.register(Associate)
class AssociateAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "user_id",
        "user__first_name",
        "user__last_name",
        "created_at",
    ]
    list_per_page = 25
    list_select_related = True
    raw_id_fields = ["user", "created_by"]
    search_fields = ["user__id"]
