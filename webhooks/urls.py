from django.urls import path, include

urlpatterns = [
    path("bugspeaks/", include("webhooks.bugspeaks.urls")),
]
