from django.urls import path

from test_kit_assignment import views

app_name = "test_kit_assignment"

urlpatterns = [
    path(
        "customer/",
        views.TestKitEligibleCustomerListView.as_view(),
        name="eligible-customers",
    ),
    path(
        "assign/",
        views.TestKitAssignmentCreateView.as_view(),
        name="assign",
    ),
    path(
        "assignment-history/",
        views.TestKitAssignmentHistoryListView.as_view(),
        name="assignment-history",
    ),
]
