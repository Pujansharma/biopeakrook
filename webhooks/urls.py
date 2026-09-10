from django.urls import path, include

urlpatterns = [
    path("bugspeaks/", include("webhooks.bugspeaks.urls")),
    path("strand-genomics/", include("webhooks.strand_genomics.urls")),
    path("metsights/", include("webhooks.metsights.urls")),
    path("orange-labs/", include("webhooks.orange_labs.urls")),
    path("whatsapp/", include("webhooks.whatsapp.urls")),
]
