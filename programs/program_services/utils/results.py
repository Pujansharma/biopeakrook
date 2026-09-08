# Define the functions here for the partners
# Each handler receives result_request instance & provider_api_data dict
from integrations.bugspeaks.utils import BUGSPEAKS_HANDLER
from products.utils.constants import ProviderCallbackFunction

PROVIDER_HANDLER = {
    ProviderCallbackFunction.BUGSPEAKS: BUGSPEAKS_HANDLER,
}


def get_result_fetch_handler(provider_callback, product_callback):
    provider_handler = PROVIDER_HANDLER.get(provider_callback) or {}
    # Return None if not found
    if not provider_handler:
        return None
    result_handler = provider_handler.get(product_callback) or (lambda *x, **y: None)
    return result_handler
