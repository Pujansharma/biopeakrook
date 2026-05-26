from django.contrib import admin

from .models import Associate, AssociateCenterAssignment


@admin.register(Associate)
class AssociateAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "user_id",
        "contact_phone",
        "user__first_name",
        "user__last_name",
        "created_at",
    ]
    list_per_page = 25
    list_select_related = True
    raw_id_fields = ["user", "created_by"]
    search_fields = ["user__id", "user__email", "contact_phone"]


@admin.register(AssociateCenterAssignment)
class AssociateCenterAssignmentAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "get_associate_email",
        "get_center_name",
        "get_role_name",
        "mode",
        "is_primary",
        "is_admin",
        "is_care_staff",
        "created_at",
    ]
    list_per_page = 25
    list_select_related = True
    raw_id_fields = ["associate", "center", "role", "created_by"]
    search_fields = [
        "associate__user__email",
        "associate__contact_phone",
        "center__name",
    ]

    @admin.display(description="Associate Email", ordering="associate__user__email")
    def get_associate_email(self, obj: AssociateCenterAssignment) -> str:
        return obj.associate.user.email

    @admin.display(description="Center", ordering="center__name")
    def get_center_name(self, obj: AssociateCenterAssignment) -> str:
        return obj.center.name

    @admin.display(description="Role", ordering="role__name")
    def get_role_name(self, obj: AssociateCenterAssignment) -> str | None:
        return obj.role.name if obj.role else None