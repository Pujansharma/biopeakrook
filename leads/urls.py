from django.urls import path

from leads import views

urlpatterns = [
    path("v2/", views.LeadsV2View.as_view()),
    path("v2/<uuid:pk>/", views.LeadV2DetailView.as_view()),
    path("v2/<uuid:pk>/convert-client/", views.LeadConvertClientView.as_view()),
    path("", views.LeadsView.as_view()),
    path("<uuid:pk>/", views.LeadDetailView.as_view()),
    path("<uuid:pk>/convert-client/", views.LeadConvertClientView.as_view()),
]
