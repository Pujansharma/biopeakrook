from django.urls import path

from . import views

urlpatterns = [
    path("register/firebase/", views.FirebaseRegistrationView.as_view()),
]
