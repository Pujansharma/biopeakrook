from django.contrib import admin

from test_kit_assignment.models import TestKitAssignment


@admin.register(TestKitAssignment)
class TestKitAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "assigned_to",
        "handover_type",
        "status",
        "assigned_on",
        "clinic",
        "created_by",
        "is_kit_journey_visible",
    ]
    list_filter = ["handover_type", "status", "is_kit_journey_visible"]
    search_fields = [
        "assigned_to__first_name",
        "assigned_to__last_name",
        "assigned_to__customer__user__phone",
        "clinic__name",
    ]
    raw_id_fields = ["assigned_to", "clinic", "created_by"]
    filter_horizontal = ["products"]
    readonly_fields = ["created_at", "updated_at"]
