from django.conf import settings
from django.urls import path, include
from django.views.generic import RedirectView
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.utils.defaults import HomePageView

urlpatterns = [
    path("", HomePageView.as_view()),
    path(
        "erd/",
        serve,
        {"document_root": settings.BASE_DIR / "docs", "path": "schema-erd.html"},
        name="schema-erd",
    ),
    path("openapi/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path(
        "openapi/docs/",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="openapi-docs",
    ),
    path(
        "schema/",
        RedirectView.as_view(pattern_name="openapi-schema", permanent=True),
    ),
    path(
        "docs/",
        RedirectView.as_view(pattern_name="openapi-docs", permanent=True),
    ),
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
    path("leads/", include("leads.urls")),
    path("webhooks/", include("webhooks.urls")),
    path("pre-consultation/", include("pre_consultation.urls")),
]
