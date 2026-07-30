from django.urls import path

from programs.composites import views

urlpatterns = [
    path(
        "templates/",
        views.CompositeTemplatesView.as_view(),
    ),
    path(
        "templates/<uuid:pk>/",
        views.CompositeTemplateDetailView.as_view(),
    ),
    path(
        "templates/<uuid:pk>/services/",
        views.CompositeTemplateServicesListView.as_view(),
    ),
    path(
        "services/<uuid:service_id>/prerequisites/",
        views.CompositeServicePrerequisiteDetailView.as_view(),
    ),
    path(
        "prerequisites/<uuid:service_id>/prerequisite-services/",
        views.CompositePrerequisiteServicesListView.as_view(),
    ),
    path(
        "prerequisites/<uuid:service_id>/available-prerequisite-services/",
        views.CompositeAvailablePrerequisiteServicesListView.as_view(),
    ),
    path(
        "programs/<uuid:pk>/",
        views.CompositeProgramDetailView.as_view(),
    ),
    path(
        "programs/<uuid:pk>/services/",
        views.CompositeProgramServicesListView.as_view(),
    ),
    path(
        "programs/<uuid:pk>/cancel/",
        views.CompositeProgramCancelView.as_view(),
    ),
]
