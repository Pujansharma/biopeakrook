from django.contrib import admin

from .models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)


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


@admin.register(AssociateRole)
class AssociateRoleAdmin(admin.ModelAdmin):
    readonly_fields = ["id", "created_at", "updated_at"]
    list_display = [
        "name",
        "center",
        "role_tag",
        "is_external",
        "is_system",
        "created_at",
    ]
    list_per_page = 25
    list_select_related = True
    list_filter = ["role_tag", "is_external", "is_system"]
    raw_id_fields = ["center", "created_by"]
    search_fields = ["name", "center__name"]


class AssociateCenterAssignmentRoleInline(admin.TabularInline):
    model = AssociateCenterAssignmentRole
    extra = 0
    raw_id_fields = ["role"]


@admin.register(AssociateCenterAssignment)
class AssociateCenterAssignmentAdmin(admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]
    list_display = [
        "get_associate_email",
        "get_center_name",
        "get_role_names",
        "mode",
        "is_primary",
        "is_admin",
        "is_care_staff",
        "created_at",
    ]
    list_per_page = 25
    list_select_related = True
    raw_id_fields = ["associate", "center", "created_by"]
    search_fields = [
        "associate__user__email",
        "associate__contact_phone",
        "center__name",
    ]
    inlines = [AssociateCenterAssignmentRoleInline]

    @admin.display(description="Associate Email", ordering="associate__user__email")
    def get_associate_email(self, obj: AssociateCenterAssignment) -> str:
        return obj.associate.user.email

    @admin.display(description="Center", ordering="center__name")
    def get_center_name(self, obj: AssociateCenterAssignment) -> str:
        return obj.center.name

    @admin.display(description="Roles")
    def get_role_names(self, obj: AssociateCenterAssignment) -> str:
        names = [
            link.role.name
            for link in obj.role_links.all()
            if link.is_active and link.role.is_active
        ]
        return ", ".join(names) if names else "-"
