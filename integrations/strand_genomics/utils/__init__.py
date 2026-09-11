from products.utils.constants import ProductCallbackFunction
from .results import handle_strand_nutri_dna_report_fetch, handle_strand_ghi_report_fetch

STRAND_GENOMICS_HANDLER = {
    ProductCallbackFunction.GENOMICS_NUTRI_DNA: handle_strand_nutri_dna_report_fetch,
    ProductCallbackFunction.GENOMICS_HEALTH_INSIGHTS: handle_strand_ghi_report_fetch,
}
