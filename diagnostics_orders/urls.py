from django.urls import path

from diagnostics_orders import views

app_name = "diagnostics_orders"

urlpatterns = [
    path(
        "eligible-customers/",
        views.EligibleCustomersListView.as_view(),
        name="eligible-customers",
    ),
    path(
        "check-timeslots/",
        views.CheckTimeslotsView.as_view(),
        name="check-timeslots",
    ),
    path(
        "test-packages/",
        views.TestPackagesListView.as_view(),
        name="test-packages",
    ),
    path(
        "add-test-package/",
        views.AddTestPackageView.as_view(),
        name="add-test-package",
    ),
    path(
        "create-order/",
        views.CreateOrderView.as_view(),
        name="create-order",
    ),
    path(
        "orders/",
        views.OrdersListView.as_view(),
        name="orders",
    ),
    path(
        "order/<str:request_id>/",
        views.OrderDetailView.as_view(),
        name="order-detail",
    ),
    path(
        "order/reschedule/<str:request_id>/",
        views.RescheduleOrderView.as_view(),
        name="order-reschedule",
    ),
    path(
        "order/cancel/<str:request_id>/",
        views.CancelOrderView.as_view(),
        name="order-cancel",
    ),
]
