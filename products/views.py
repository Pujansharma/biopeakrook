from django.db.models import ProtectedError, RestrictedError, Q

from accounts.utils.permissions import IsAdminUser
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)
from products.models import Product
from products.serializers import ProductSerializer


class ProductsView(BaseListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()

        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        qs = Product.objects.select_related("created_by").filter()
        return qs

    def perform_create(self, serializer: ProductSerializer):
        serializer.save(created_by=self.request.user)


class ProductDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Product.objects.select_related("created_by").filter()
        return qs

    def perform_destroy(self, instance: Product):
        try:
            super().perform_destroy(instance)
        except ProtectedError, RestrictedError:
            self.raise_bad_request("This product cannot be deleted")
