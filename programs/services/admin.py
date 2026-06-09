from django.contrib import admin

from programs.services.models import Service, CenterServiceAssignment


class CenterServiceAssignmentInline(admin.TabularInline):
    model = CenterServiceAssignment
    extra = 1
    raw_id_fields = ["center"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fields = ["center", "is_active", "created_at", "updated_at"]
    can_delete = True


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["id", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["id", "name"]
    raw_id_fields = ["created_by"]
    inlines = [CenterServiceAssignmentInline]
    list_per_page = 25


@admin.register(CenterServiceAssignment)
class CenterServiceAssignmentAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = ["service", "center", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["service__name", "center__name"]
    raw_id_fields = ["service", "center"]
    list_per_page = 50
