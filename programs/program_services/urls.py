from django.urls import path

from programs.program_services import views

urlpatterns = [
    path(
        "assessment-services/<uuid:pk>/",
        views.AssessmentProgramServiceDetailView.as_view(),
    ),

    path(
        "assessment-services/<uuid:pk>/providers/",
        views.AssessmentProgramServiceProviders.as_view(),
    ),

    path(
        "assessment-services/<uuid:pk>/products/",
        views.AssessmentProgramServiceProducts.as_view(),
    ),

    path(
        "assessment-services/<uuid:pk>/results/",
        views.AssessmentProgramServiceResultsView.as_view(),
    ),
    path(
        "assessment-services/<uuid:pk>/documents/",
        views.AssessmentProgramServiceDocumentsView.as_view(),
    ),
    path(
        "therapy-services/<uuid:pk>/",
        views.TherapyProgramServiceDetailView.as_view(),
    ),
    path(
        "results/<uuid:pk>/",
        views.ServiceResultDetailView.as_view(),
    ),
    path(
        "results/<uuid:pk>/documents/",
        views.ServiceResultDocumentsView.as_view(),
    ),
]
