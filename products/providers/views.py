from django.db.models import Q, ProtectedError

from accounts.utils.permissions import IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseGenericAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseCreateAPIView,
)
from products.models import Provider, ProviderAPI
from products.serializers import ProviderSerializer, ProviderAPISerializer
from products.utils.constants import get_callback_options


class ProviderCallbackOptionsView(BaseGenericAPIView):
    permission_classes = [IsAdminUser]

    @classmethod
    def get_provider_code(cls, provider_id):
        provider = Provider.objects.filter(pk__iexact=provider_id).first()
        if not provider:
            return None
        return provider.callback

    def get(self, request):
        provider_query = request.query_params.get("provider", "").strip()
        provider_filter = self.get_provider_code(provider_query)
        data = get_callback_options(provider_filter)
        return self.send_response("Callback options retrieved.", data)


class ProviderListView(BaseListCreateAPIView):
    serializer_class = ProviderSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query_param = self.request.query_params.get("search", "").strip()
        active_query_param = self.request.query_params.get("active", None)
        if active_query_param and active_query_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query_param))
        if search_query_param:
            search |= Q(name__istartswith=search_query_param)
            search |= Q(name__icontains=search_query_param)
            search |= Q(code__iexact=search_query_param)

        qs = (
            Provider.objects.select_related("created_by", "api")
            .prefetch_related("products")
            .annotate(has_api=Q(api__isnull=False))
            .filter(search, **filter_kwargs)
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProviderDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = ProviderSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = (
            Provider.objects.select_related("created_by", "api")
            .annotate(has_api=Q(api__isnull=False))
            .filter()
            .order_by("-created_at")
        )
        return qs

    def perform_destroy(self, instance: Provider):
        try:
            super().perform_destroy(instance)
        except (ProtectedError,):
            self.raise_bad_request("This provider cannot be deleted")


class ProviderAPIListView(BaseCreateAPIView, BaseRetrieveUpdateDestroyAPIView):
    serializer_class = ProviderAPISerializer
    permission_classes = [IsAdminUser]

    def get_provider(self):
        qs = Provider.objects.select_related("created_by")
        return get_object_or_404(
            qs, "No provider found with the given ID", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        search = Q()
        provider = self.get_provider()
        search_params = self.request.query_params.get("search", "").strip()

        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        qs = ProviderAPI.objects.select_related(
            "provider", "provider__created_by"
        ).filter(search, provider=provider)
        return qs

    def perform_create(self, serializer):
        serializer.save(_provider=self.get_provider(), created_by=self.request.user)
