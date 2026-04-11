from django.urls import path

from . import views

urlpatterns = [
    path('account/', views.CustomerAccountProfileView.as_view()),
    path('profiles/', views.CustomerProfilesListView.as_view()),
]
