"""Scoped OpenAPI schema and Swagger UI for pre-consultation endpoints."""

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from pre_consultation.utils.schema import PRE_CONSULTATION_SPECTACULAR_SETTINGS


class PreConsultationSpectacularAPIView(SpectacularAPIView):
    custom_settings = PRE_CONSULTATION_SPECTACULAR_SETTINGS


class PreConsultationSpectacularSwaggerView(SpectacularSwaggerView):
    pass
