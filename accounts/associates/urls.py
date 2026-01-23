from django.urls import path

from . import views

urlpatterns = [
    path('', views.AssociateView.as_view()),
    path('<uuid:pk>/', views.AssociateDetailView.as_view()),
]
