# Define the functions here for the partners
# Each handler receives result_request instance & provider_api_data dict
from integrations.bugspeaks.utils import BUGSPEAKS_HANDLER
from integrations.five_c_networks.utils import FIVE_C_NETWORK_HANDLER
from integrations.strand_genomics.utils import STRAND_GENOMICS_HANDLER
from products.utils.constants import ProviderCallbackFunction

PROVIDER_HANDLER = {
    ProviderCallbackFunction.BUGSPEAKS: BUGSPEAKS_HANDLER,
    ProviderCallbackFunction.FIVE_C_NETWORK: FIVE_C_NETWORK_HANDLER,
    ProviderCallbackFunction.STRAND_LIFE_SCIENCES: STRAND_GENOMICS_HANDLER,
}


def get_result_fetch_handler(provider_callback, product_callback):
    provider_handler = PROVIDER_HANDLER.get(provider_callback) or {}
    # Return None if not found
    if not provider_handler:
        return None
    result_handler = provider_handler.get(product_callback)
    return result_handler
