from django.urls import path

from integrations.communications.app_download import AppDownloadRedirectView

urlpatterns = [
    path("", AppDownloadRedirectView.as_view(), name="app-download-redirect"),
]
