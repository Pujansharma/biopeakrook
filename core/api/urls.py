from django.urls import path, include

from core.utils.defaults import HomePageView

urlpatterns = [
    path('', HomePageView.as_view()),
    path('auth/', include('accounts.urls')),
    path('users/', include('accounts.users.urls')),

    # Centers
    path('centers/', include('accounts.centers.urls')),

    # Associates
    path('associates/', include('accounts.associates.urls')),
    path('admins/', include('accounts.admins.urls')),
]
