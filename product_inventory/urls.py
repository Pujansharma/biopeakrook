from django.urls import path

from product_inventory import views

app_name = "product_inventory"

urlpatterns = [
    path("specs/", views.ProductInventorySpecsView.as_view(), name="specs"),
    path(
        "consignment/",
        views.ProductInventoryConsignmentView.as_view(),
        name="consignment",
    ),
    path("all/", views.ProductInventoryAllView.as_view(), name="all"),
    path("batches/", views.ProductInventoryBatchesView.as_view(), name="batches"),
]
