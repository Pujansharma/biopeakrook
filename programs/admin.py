from django.contrib import admin

from programs.models import (
    Program,
    ProgramService,
    TherapyProgram,
    TherapyProgramService,
)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = [
        "id",
        "customer_profile",
        "center",
        "program_type",
        "is_complimentary",
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


@admin.register(TherapyProgram)
class TherapyProgramAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "program_id",
        "sessions_count",
        "sessions_used",
        "sessions_cancelled",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["program__id"]
    raw_id_fields = ["program"]
    list_select_related = True
    list_per_page = 25


@admin.register(TherapyProgramService)
class TherapyProgramServiceAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "program_service_id",
        "sessions_count",
        "sessions_used",
        "sessions_cancelled",
        "redeem_code",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = [
        "program_service__id",
        "program_service__program__id",
        "program_service__service__name",
        "redeem_code",
    ]
    raw_id_fields = ["program_service"]
    list_select_related = [
        "program_service",
        "program_service__program",
        "program_service__service",
    ]
    list_per_page = 25
