from drf_spectacular.extensions import OpenApiAuthenticationExtension


class BaseJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.utils.authentication.BaseJWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
