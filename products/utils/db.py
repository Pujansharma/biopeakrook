from uuid import UUID

from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from products.models import Product, Provider


def update_provider_products_count(provider_id: UUID) -> None:
    subquery = (
        Product.objects.filter(provider=OuterRef("pk"))
        .values("provider")
        .annotate(count=Count("pk"))
        .values("count")
    )
    Provider.objects.filter(pk=provider_id).update(
        products_count=Coalesce(Subquery(subquery), Value(0))
    )


def update_all_provider_products_count() -> int:
    subquery = (
        Product.objects.filter(provider=OuterRef("pk"))
        .values("provider")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return Provider.objects.update(
        products_count=Coalesce(Subquery(subquery), Value(0))
    )
