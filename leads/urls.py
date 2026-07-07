from django.urls import path

from leads import views

urlpatterns = [
    path("", views.LeadsView.as_view()),
    path("<uuid:pk>/", views.LeadDetailView.as_view()),
    path("<uuid:pk>/share-onboarding/", views.LeadShareOnboardingView.as_view()),
    path("<uuid:pk>/convert-client/", views.LeadConvertClientView.as_view()),
    path("<uuid:pk>/available-packages/", views.LeadAvailablePackagesView.as_view()),
    path("<uuid:pk>/assign-package/", views.LeadAssignPackageView.as_view()),
    path("<uuid:pk>/packages/", views.LeadPackagesView.as_view()),
]
