from django.urls import path

from wearables.views import HealthDashboardView, HealthDomainView, HealthTimelineView

urlpatterns = [
    path("dashboard/", HealthDashboardView.as_view(), name="health-dashboard"),
    path("timeline/", HealthTimelineView.as_view(), name="health-timeline"),
    path("<str:domain>/", HealthDomainView.as_view(), name="health-domain"),
]

