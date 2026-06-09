from django.contrib import admin

from programs.models import Program, ProgramService, WellnessProgram


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "sessions_used", "created_at", "updated_at"]
    list_display = [
        "id",
        "customer_profile",
        "center",
        "program_type",
        "is_complimentary",
        "sessions_count",
        "sessions_used",
        "created_at",
    ]
    list_filter = ["is_active", "program_type", "is_complimentary"]
    search_fields = ["id", "customer_profile__customer__user__phone"]
    raw_id_fields = ["customer_profile", "center"]
    filter_horizontal = ["redeemable_centers"]
    list_select_related = True
    list_per_page = 25


@admin.register(ProgramService)
class ProgramServiceAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "program", "service", "created_by", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["id", "program__id", "service__name"]
    raw_id_fields = ["program", "service", "created_by"]
    list_select_related = True
    list_per_page = 25


@admin.register(WellnessProgram)
class WellnessProgramAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "program", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["id", "program__id"]
    raw_id_fields = ["program"]
    list_select_related = True
    list_per_page = 25
