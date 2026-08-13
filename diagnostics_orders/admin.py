from django.contrib import admin

from diagnostics_orders.models import (
    CatalogCityPrice,
    CatalogItem,
    DiagnosticOrder,
    DiagnosticOrderCustomer,
    DiagnosticOrderEvent,
    DiagnosticOrderLine,
    DiagnosticOrderRescheduleHistory,
    DiagnosticsOrdersSummary,
)


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = (
        "diagnostic_test_id",
        "name",
        "category",
        "is_custom_package",
        "fasting_required",
        "is_active",
    )
    list_filter = ("category", "is_custom_package", "fasting_required", "is_active")
    search_fields = ("name", "diagnostic_test_id")


@admin.register(CatalogCityPrice)
class CatalogCityPriceAdmin(admin.ModelAdmin):
    list_display = ("catalog_item", "city", "price", "tat_in_hours", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("catalog_item__name", "catalog_item__diagnostic_test_id")


class DiagnosticOrderCustomerInline(admin.TabularInline):
    model = DiagnosticOrderCustomer
    extra = 0


@admin.register(DiagnosticOrder)
class DiagnosticOrderAdmin(admin.ModelAdmin):
    list_display = (
        "request_id",
        "status",
        "city",
        "slot_datetime",
        "total_price",
        "created_at",
    )
    list_filter = ("status", "city")
    search_fields = ("request_id", "address")
    inlines = [DiagnosticOrderCustomerInline]
    readonly_fields = (
        "token",
        "raw_create_response",
    )


@admin.register(DiagnosticOrderLine)
class DiagnosticOrderLineAdmin(admin.ModelAdmin):
    list_display = (
        "order_customer",
        "category",
        "diagnostic_test_id",
        "name",
        "price",
    )
    list_filter = ("category",)


@admin.register(DiagnosticOrderEvent)
class DiagnosticOrderEventAdmin(admin.ModelAdmin):
    list_display = ("order", "event_type", "orange_event_id", "created_at")
    search_fields = ("order__request_id", "event_type", "orange_event_id")


@admin.register(DiagnosticOrderRescheduleHistory)
class DiagnosticOrderRescheduleHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "previous_slot_datetime",
        "new_slot_datetime",
        "reason",
        "rescheduled_by",
        "created_at",
    )
    search_fields = ("order__request_id", "reason")
    raw_id_fields = ("order", "rescheduled_by")


@admin.register(DiagnosticsOrdersSummary)
class DiagnosticsOrdersSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "total_orders",
        "total_rescheduled",
        "total_cancelled",
        "total_completed",
    )
