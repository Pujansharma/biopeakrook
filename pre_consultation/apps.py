from django.apps import AppConfig


class PreConsultationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pre_consultation"

    def ready(self) -> None:
        import core.utils.openapi  # noqa: F401
