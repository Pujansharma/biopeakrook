from django.urls import include, path

urlpatterns = [
    path("session/", include("pre_consultation.session.urls")),
]
