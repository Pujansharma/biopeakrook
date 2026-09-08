from django.urls import path

from programs.program_services import views

urlpatterns = [
    path(
        "assessment-services/<uuid:pk>/",
        views.AssessmentProgramServiceDetailView.as_view(),
    ),
    path(
        "assessment-services/<uuid:pk>/cancel/",
        views.AssessmentProgramServiceCancelView.as_view(),
    ),
    path(
        "assessment-services/<uuid:pk>/providers/",
        views.AssessmentProgramServiceProviders.as_view(),
    ),

    path(
        "assessment-services/<uuid:pk>/products/",
        views.AssessmentProgramServiceProducts.as_view(),
    ),

    # Upload documents flow: Results first, then files in them
    path(
        "assessment-services/<uuid:pk>/results/",
        views.AssessmentProgramServiceResultsView.as_view(),
    ),
    path(
        "assessment-services/<uuid:pk>/documents/",
        views.AssessmentProgramServiceDocumentsView.as_view(),
    ),

    # Therapy service details
    path(
        "therapy-services/<uuid:pk>/",
        views.TherapyProgramServiceDetailView.as_view(),
    ),
    path(
        "therapy-services/<uuid:pk>/cancel/",
        views.TherapyProgramServiceCancelView.as_view(),
    ),
    path(
        "consultation-services/<uuid:pk>/cancel/",
        views.ConsultationProgramServiceCancelView.as_view(),
    ),

    # Fetch requests
    path(
        "assessment-services/<uuid:pk>/result-requests/",
        views.AssessmentServiceResultRequestView.as_view(),
    ),
    path(
        "result-requests/<uuid:pk>/",
        views.ResultRequestDetailView.as_view(),
    ),
    path(
        "result-requests/<uuid:pk>/refetch/",
        views.ResultRequestRefetchView.as_view(),
    ),

    path(
        "result-requests/<uuid:pk>/cancel/",
        views.ResultRequestCancelView.as_view(),
    ),

    # Results section: Get result info and files in them
    path(
        "results/<uuid:pk>/",
        views.ServiceResultDetailView.as_view(),
    ),
    path(
        "results/<uuid:pk>/documents/",
        views.ServiceResultDocumentsView.as_view(),
    ),
]
