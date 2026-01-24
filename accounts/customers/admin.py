from django.contrib import admin

from accounts.customers.models import Customer


# Register your models here.
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    readonly_fields = ['created_at', 'updated_at']
    list_filter = ['is_active']
    list_display = ['user_id', 'center', 'created_at']
    raw_id_fields = ['center', 'user']
