from django.urls import path

from . import views

urlpatterns = [path("", views.StrandGenomicsWebhookView.as_view())]
