from django.urls import path, include

from core.utils.defaults import HomePageView

urlpatterns = [
    path("", HomePageView.as_view()),
    path("auth/", include("accounts.urls")),
    path("users/", include("accounts.users.urls")),
    path("notifications/", include("accounts.notifications.urls")),
    # Organizations
    path("organizations/", include("accounts.organizations.urls")),
    # External
    path("external/", include("external.urls")),
    # Centers
    path("centers/", include("accounts.centers.urls")),
    # Associates
    path("associates/", include("accounts.associates.urls")),
    path("admins/", include("accounts.admins.urls")),
    # Customer-profiles
    path("profiles/", include("accounts.customers.urls")),
    # Admin level actions
    path("products/", include("products.urls")),
    path("programs/", include("programs.urls")),
    path("services/", include("programs.services.urls")),
    path("webhooks/", include("webhooks.urls")),
    path("pre-consultation/", include("pre_consultation.urls")),
]
