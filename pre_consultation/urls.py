"""URL routes for pre-consultation session and layer endpoints."""

from django.urls import path
from django.views.generic import RedirectView

from pre_consultation.layer_views import (
    PatientBaselineLayerView,
    PatientCategoryLayerView,
    PatientClusterProbeLayerView,
    PatientConcernLayerView,
    PatientConcernProbeLayerView,
    PatientGoalsPrioritiesLayerView,
    PatientLifestyleEnvironmentLayerView,
    PatientSymptomLayerView,
)
from pre_consultation.medical_history_layer_view import (
    PatientMedicalHistoryContextLayerView,
)
from pre_consultation.openapi_views import (
    PreConsultationSpectacularAPIView,
    PreConsultationSpectacularSwaggerView,
)
from pre_consultation.views import (
    PreConsultationSessionCompleteView,
    PreConsultationSessionResultView,
    PreConsultationSessionStartView,
)

urlpatterns = [
    path(
        "openapi/",
        PreConsultationSpectacularAPIView.as_view(),
        name="pre-consultation-openapi",
    ),
    path(
        "openapi/docs/",
        PreConsultationSpectacularSwaggerView.as_view(
            url_name="pre-consultation-openapi",
        ),
        name="pre-consultation-openapi-docs",
    ),
    path(
        "schema/",
        RedirectView.as_view(
            pattern_name="pre-consultation-openapi",
            permanent=True,
        ),
    ),
    path(
        "docs/",
        RedirectView.as_view(
            pattern_name="pre-consultation-openapi-docs",
            permanent=True,
        ),
    ),
    path(
        "session/start/",
        PreConsultationSessionStartView.as_view(),
        name="session-start",
    ),
    path(
        "session/complete/",
        PreConsultationSessionCompleteView.as_view(),
        name="session-complete",
    ),
    path(
        "session/result/",
        PreConsultationSessionResultView.as_view(),
        name="session-result",
    ),
    path(
        "session/patient_baseline/",
        PatientBaselineLayerView.as_view(),
        name="session-patient-baseline",
    ),
    path(
        "session/patient_category/",
        PatientCategoryLayerView.as_view(),
        name="session-patient-category",
    ),
    path(
        "session/patient_concern/",
        PatientConcernLayerView.as_view(),
        name="session-patient-concern",
    ),
    path(
        "session/patient_symptom/",
        PatientSymptomLayerView.as_view(),
        name="session-patient-symptom",
    ),
    path(
        "session/patient_concern_probe/",
        PatientConcernProbeLayerView.as_view(),
        name="session-patient-concern-probe",
    ),
    path(
        "session/patient_cluster_probe/",
        PatientClusterProbeLayerView.as_view(),
        name="session-patient-cluster-probe",
    ),
    path(
        "session/patient_medical_history_context/",
        PatientMedicalHistoryContextLayerView.as_view(),
        name="session-patient-medical-history-context",
    ),
    path(
        "session/patient_lifestyle_environment/",
        PatientLifestyleEnvironmentLayerView.as_view(),
        name="session-patient-lifestyle-environment",
    ),
    path(
        "session/patient_goals_priorities/",
        PatientGoalsPrioritiesLayerView.as_view(),
        name="session-patient-goals-priorities",
    ),
]
