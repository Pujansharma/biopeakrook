from products.utils.constants import ProductCallbackFunction
from .results import handle_bugspeaks_report_fetch

BUGSPEAKS_HANDLER = {
    ProductCallbackFunction.GUT_MICROBIOME: handle_bugspeaks_report_fetch
}
