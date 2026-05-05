from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include

admin.site.site_header = "Biopeak Nexus Admin Dashboard"
admin.site.site_title = "Biopeak Nexus Dashboard"
admin.site.index_title = "Biopeak Nexus Dashboard"

urlpatterns = [
    path("", include("core.api.urls")),
    path(
        "admin/password_reset/",
        auth_views.PasswordResetView.as_view(
            html_email_template_name="registration/html_password_reset_template.html"
        ),
        name="admin_password_reset",
    ),
    path(
        "admin/password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("admin/", admin.site.urls),
    path("__debug__/", include("debug_toolbar.urls")),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler500 = "core.utils.exceptions.server_error"
handler404 = "core.utils.exceptions.not_found"
