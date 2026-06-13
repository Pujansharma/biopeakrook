from django.urls import path, include

urlpatterns = [
    path("therapy-programs/", include("programs.therapy.urls")),
    path("assessment-programs/", include("programs.assessment.urls")),
    path("consultation-programs/", include("programs.consultation.urls")),
]
