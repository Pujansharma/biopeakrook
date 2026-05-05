from django.contrib import admin

from accounts.admins.models import Admin


@admin.register(Admin)
class AdminUserAdmin(admin.ModelAdmin):
    readonly_fields = ['created_at', 'updated_at']
    list_display = [ 'user__email', 'user__first_name', 'user__last_name', 'created_at']
    list_select_related = True
    list_per_page = 25
    search_fields = ['user__email']
    raw_id_fields = ['user']
