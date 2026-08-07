from django.urls import path

from test_kit_inventory import views

app_name = "test_kit_inventory"

urlpatterns = [
    path("specs/", views.TestKitInventorySpecsView.as_view(), name="specs"),
    path(
        "consignment/",
        views.TestKitInventoryConsignmentView.as_view(),
        name="consignment",
    ),
    path("all/", views.TestKitInventoryAllView.as_view(), name="all"),
    path("batches/", views.TestKitInventoryBatchesView.as_view(), name="batches"),
    path(
        "customer/",
        views.TestKitInventoryEligibleCustomerListView.as_view(),
        name="eligible-customers",
    ),
    path(
        "assign/",
        views.TestKitInventoryAssignmentCreateView.as_view(),
        name="assign",
    ),
    path(
        "assignment-history/",
        views.TestKitInventoryAssignmentHistoryListView.as_view(),
        name="assignment-history",
    ),
    path(
        "providers/add/",
        views.ProviderCreateView.as_view(),
        name="provider-add",
    ),
    path(
        "products/add/",
        views.ProductCreateView.as_view(),
        name="product-add",
    ),
]
