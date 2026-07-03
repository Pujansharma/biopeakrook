from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.users.models import User
from core.utils.fields import PhoneNumberFormField


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "phone":
            kwargs["form_class"] = PhoneNumberFormField
            kwargs["region"] = "IN"
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    list_display = (
        "id",
        "email",
        "phone",
        "is_staff",
        "date_joined",
    )
    fieldsets = (
        (
            "General info",
            {
                "fields": (
                    "email",
                    "phone",
                    "password",
                )
            },
        ),
        (
            "Profile",
            {"fields": ("first_name", "last_name", "date_of_birth", "gender", "image")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Access Level",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        ("System Data", {"fields": ("id", "date_joined", "last_login", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )
    ordering = ("-date_joined",)
    list_filter = (
        "is_staff",
        "is_active",
    )
    search_fields = (
        "id",
        "email",
        "phone",
    )
    readonly_fields = (
        "id",
        "date_joined",
        "last_login",
        "updated_at",
    )
    list_per_page = 25
