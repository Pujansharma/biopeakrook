from django.urls import path

from . import views

urlpatterns = [path("", views.BugspeaksWebhookView.as_view())]
