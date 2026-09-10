from django.contrib import admin

from accounts.centers.models import Center, CenterOperatingHour, CenterClosure


@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    readonly_fields = [
        "id",
        "code",
        "staff_count",
        "inactive_staff_count",
        "customer_count",
        "inactive_customer_count",
        "created_at",
        "updated_at",
    ]
    list_display = [
        "id",
        "code",
        "name",
        "modes",
        "status",
        "staff_count",
        "inactive_staff_count",
        "customer_count",
        "inactive_customer_count",
        "created_at",
    ]
    list_filter = ["is_active", "modes", "status"]
    search_fields = ["id", "name", "code"]
    raw_id_fields = ["created_by"]


@admin.register(CenterOperatingHour)
class CenterOperatingHoursAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "center", "is_open", "created_at"]
    list_select_related = True
    raw_id_fields = ["center"]
    list_filter = ["is_open", "is_active"]
    search_fields = ["center__name", "center__id"]


@admin.register(CenterClosure)
class CenterClosureAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "center", "date", "type", "reason", "created_at"]
    list_select_related = True
    raw_id_fields = ["center"]
    list_filter = ["is_active", "type"]
    search_fields = ["center__name", "center__id", "reason"]
