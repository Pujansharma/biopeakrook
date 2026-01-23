from django.contrib import admin

from accounts.centers.models import Center, CenterOperatingHour, CenterHoliday


# Register your models here.
@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'code', 'created_at', 'updated_at']
    list_display = ['id', 'code', 'name', 'modes', 'status', 'created_at']
    list_filter = ['is_active', 'modes', 'status']
    search_fields = ['id', 'name', 'code']


@admin.register(CenterOperatingHour)
class CenterOperatingHoursAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'center', 'is_open', 'created_at']
    list_select_related = True
    raw_id_fields = ['center']
    list_filter = ['is_open', 'is_active']
    search_fields = ['center__name', 'center__id']


@admin.register(CenterHoliday)
class CenterHolidayAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'center', 'date', 'created_at']
    list_select_related = True
    raw_id_fields = ['center']
    list_filter = ['is_active']
    search_fields = ['center__name', 'center__id']
