from functools import partial

from django.db import models


class ProviderCallbackFunction(models.TextChoices):
    BIOPEAK = "biopeak", "Biopeak"
    METSIGHTS = "metsights", "MetSights"
    HEALTHIANS = "healthians", "Healthians"


class ProductCallbackFunction(models.TextChoices):
    BLOOD = "blood", "Blood Diagnostics"
    DXA = "dxa", "DXA Scan"


PROVIDER_PRODUCT_CALLBACK_MAP: dict[str, list[ProductCallbackFunction]] = {
    ProviderCallbackFunction.BIOPEAK: [
        ProductCallbackFunction.BLOOD,
        ProductCallbackFunction.DXA,
    ],
    ProviderCallbackFunction.HEALTHIANS: [
        ProductCallbackFunction.BLOOD,
    ],
    ProviderCallbackFunction.METSIGHTS: [],
}


def _matches_provider(provider_filter: str, item: tuple[str, list]) -> bool:
    return not provider_filter or item[0] == provider_filter


def _serialize_callback(callback: ProductCallbackFunction) -> dict:
    return {"value": callback.value, "display_name": callback.label}


def _serialize_provider_entry(
    item: tuple[str, list[ProductCallbackFunction]],
) -> tuple[str, list[dict]]:
    provider, callbacks = item
    return provider, list(map(_serialize_callback, callbacks))


def get_callback_options(provider_filter: str) -> dict[str, list[dict]]:
    matches = partial(_matches_provider, provider_filter)
    source = dict(filter(matches, PROVIDER_PRODUCT_CALLBACK_MAP.items()))
    return dict(map(_serialize_provider_entry, source.items()))
