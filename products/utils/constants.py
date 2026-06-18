from functools import partial

from django.db import models


class ProviderCallbackFunction(models.TextChoices):
    BIOPEAK = "biopeak", "Biopeak"
    METSIGHTS = "metsights", "MetSights"
    HEALTHIANS = "healthians", "Healthians"
    ORANGE_LABS = "orange_labs", "Orange Labs"
    BUGSPEAKS = "bugspeaks", "BugSpeaks"


class ProductCallbackFunction(models.TextChoices):
    BLOOD = "blood", "Blood Diagnostics"
    DXA = "dxa", "DXA Scan"
    EVO_360 = "evo_360", "EVO 360"


PROVIDER_PRODUCT_CALLBACK_MAP: dict[str, list[ProductCallbackFunction]] = {
    ProviderCallbackFunction.BIOPEAK: [
        ProductCallbackFunction.BLOOD,
        ProductCallbackFunction.DXA,
    ],
    ProviderCallbackFunction.HEALTHIANS: [
        ProductCallbackFunction.BLOOD,
    ],
    ProviderCallbackFunction.METSIGHTS: [],
    ProviderCallbackFunction.ORANGE_LABS: [ProductCallbackFunction.BLOOD],
    ProviderCallbackFunction.BUGSPEAKS: [
        ProductCallbackFunction.EVO_360,
    ]
}


def _matches_provider(provider_filter: str, item: tuple[str, list]) -> bool:
    return item[0] == provider_filter


def _serialize_callback(callback: ProductCallbackFunction) -> dict:
    return {"value": callback.value, "display_name": callback.label}


def _serialize_provider_entry(
        item: tuple[str, list[ProductCallbackFunction]],
) -> tuple[str, list[dict]]:
    provider, callbacks = item
    return provider, list(map(_serialize_callback, callbacks))


def get_callback_options(provider_filter: str | None) -> list[dict]:
    matches = partial(_matches_provider, provider_filter)
    source = dict(filter(matches, PROVIDER_PRODUCT_CALLBACK_MAP.items()))

    data = dict(map(_serialize_provider_entry, source.items()))
    return next(iter(data.values()), [])
