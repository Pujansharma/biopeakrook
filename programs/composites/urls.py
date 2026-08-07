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
        "services/<uuid:pk>/prerequisites/",
        views.CompositeServicePrerequisiteDetailView.as_view(),
    ),
    path(
        "prerequisites/<uuid:pk>/prerequisite-services/",
        views.CompositePrerequisiteServicesListView.as_view(),
    ),
    path(
        "prerequisites/<uuid:pk>/available-prerequisite-services/",
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
    path(
        "add-ons/",
        views.CompositeAddOnView.as_view(),
    ),
]
