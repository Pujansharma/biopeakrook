from django.urls import path

from . import views

urlpatterns = [
    path('', views.CentersView.as_view()),
]
