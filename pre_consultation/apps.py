"""Django app config — registers OpenAPI extensions and medical-report delete signal."""

from django.apps import AppConfig


class PreConsultationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pre_consultation"

    def ready(self) -> None:
        import core.utils.openapi  # noqa: F401
        import pre_consultation.signals  # noqa: F401
