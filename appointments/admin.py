from django.contrib import admin

from appointments.models import Schedule, BlockedPeriod, Appointment, AppointmentHistory


# Register your models here.
@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'day_of_week', 'created_at', 'valid_until']
    list_filter = ['day_of_week', 'is_active']
    list_select_related = True
    raw_id_fields = ['associate', 'center']


@admin.register(BlockedPeriod)
class BlockedPeriodAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'associate', 'created_at']
    raw_id_fields = ['associate']
    search_fields = ['associate__id', 'associate__user__email']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'associate', 'customer', 'status', 'created_at']
    list_select_related = True
    list_filter = ['is_active', 'status']
    raw_id_fields = ['associate', 'customer']
    search_fields = ['id', 'associate__user__email']


@admin.register(AppointmentHistory)
class AppointmentHistoryAdmin(admin.ModelAdmin):
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_display = ['id', 'appointment', 'created_at']
    raw_id_fields = ['appointment', 'rescheduled_by']
    list_select_related = True
