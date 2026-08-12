from django.db.models import ProtectedError, RestrictedError, Q

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseGenericAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)
from products.models import Product
from products.serializers import ProductSerializer
from products.utils.db import update_provider_products_count
from products.utils.documents import get_allowed_document_types


class ProductsView(BaseListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_params = self.request.query_params.get("search", "").strip()
        active_query_param = self.request.query_params.get("active", None)
        provider_ids = self.request.query_params.getlist("provider", [])
        if active_query_param and active_query_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query_param))
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        if provider_ids:
            filter_kwargs["provider__in"] = provider_ids
        qs = Product.objects.select_related("created_by").filter(
            search, **filter_kwargs
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProductDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Product.objects.select_related("created_by").filter()
        return qs

    def perform_destroy(self, instance: Product):
        provider = instance.provider
        try:
            super().perform_destroy(instance)
        except ProtectedError, RestrictedError:
            self.raise_bad_request("This product cannot be deleted")
        update_provider_products_count(provider.pk)


class ProductAllowedDocumentsView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        qs = Product.objects.select_related("provider")
        product = get_object_or_404(
            qs,
            "Product not found.",
            pk=self.kwargs.get("pk"),
        )
        data = get_allowed_document_types(
            product.provider.callback,
            product.callback,
        )
        return self.send_response("Allowed document types retrieved.", data)
