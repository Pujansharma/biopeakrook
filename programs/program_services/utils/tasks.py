import threading

from django.db.models import F
from django.utils import timezone

from core.utils.log import logger
from products.utils.constants import ProviderCallbackFunction, ProductCallbackFunction
from programs.program_services.utils.results import handle_bugspeaks_report_fetch
from programs.services.models import ResultRequest
from programs.services.utils.constants import ResultRequestStatus

# Define the functions here for the partners
# Each handler receives result_request instance & provider_api_data dict
RESULT_FETCH_HANDLERS = {
    (ProviderCallbackFunction.ORANGE_LABS, ProductCallbackFunction.BLOOD): lambda *x, **y: (True, None),
    (ProviderCallbackFunction.BUGSPEAKS, ProductCallbackFunction.GUT_MICROBIOME): handle_bugspeaks_report_fetch,
}


def get_result_fetch_handler(provider_callback, product_callback):
    return RESULT_FETCH_HANDLERS.get((provider_callback, product_callback))


def mark_result_request_failed(result_request_identifier, detail):
    ResultRequest.objects.filter(pk=result_request_identifier).update(
        status=ResultRequestStatus.FAILED,
        failure_detail=detail,
        completed_at=timezone.now(),
        updated_at=timezone.now(),
    )


def mark_result_request_completed(result_request_identifier):
    ResultRequest.objects.filter(
        pk=result_request_identifier,
        status=ResultRequestStatus.RUNNING,
    ).update(
        status=ResultRequestStatus.COMPLETED,
        failure_detail="",
        completed_at=timezone.now(),
        updated_at=timezone.now(),
    )


def handle_result_request(result_request):
    claimed_count = ResultRequest.objects.filter(
        pk=result_request.pk,
        status=ResultRequestStatus.QUEUED,
    ).update(
        status=ResultRequestStatus.RUNNING,
        attempts_count=F("attempts_count") + 1,
        failure_detail="",
        started_at=timezone.now(),
        completed_at=None,
        updated_at=timezone.now(),
    )
    if not claimed_count:
        return None

    handler = get_result_fetch_handler(
        result_request.product.provider.callback,
        result_request.product.callback,
    )
    if not handler:
        error_message = "Result fetching is not supported for this product."
        mark_result_request_failed(result_request.pk, error_message)
        logger.error(
            f"Result request failed: result_request_id={result_request.pk} "
            f"error={error_message}"
        )
        return None

    provider_api_data = result_request.product.provider.api.data or {}
    # Perform the handler function here
    handler(result_request, provider_api_data)
    return None


class ResultRequestThread(threading.Thread):
    def __init__(self, result_request):
        super().__init__()
        result_request_identifier = str(result_request)
        self.result_request = (
            ResultRequest.objects.select_related(
                "program_service__program",
                "product__provider__api",
                "created_by",
            )
            .filter(pk=result_request_identifier)
            .first()
        )

    def run(self):
        if not self.result_request:
            return None
        handle_result_request(self.result_request)
        return None


def start_result_request_task(result_request):
    return ResultRequestThread(result_request).start()
