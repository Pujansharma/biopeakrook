import threading

from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

from core.utils.log import logger
from programs.program_services.utils.db import update_program_service_fetch_counts
from programs.program_services.utils.results import get_result_fetch_handler
from programs.services.models import ResultRequest
from programs.services.utils.constants import ResultRequestStatus


def mark_result_request_failed(result_request_identifier, detail):
    ResultRequest.objects.filter(pk=result_request_identifier).update(
        status=ResultRequestStatus.FAILED,
        failure_detail=detail,
        completed_at=timezone.localtime(),
        updated_at=timezone.localtime(),
    )


def mark_result_request_completed(result_request_identifier):
    ResultRequest.objects.filter(
        pk=result_request_identifier,
        status=ResultRequestStatus.RUNNING,
    ).update(
        status=ResultRequestStatus.COMPLETED,
        failure_detail="",
        completed_at=timezone.localtime(),
        updated_at=timezone.localtime(),
    )


def handle_result_request(result_request):
    claimed_count = ResultRequest.objects.filter(
        pk=result_request.pk,
        status=ResultRequestStatus.QUEUED,
    ).update(
        status=ResultRequestStatus.RUNNING,
        attempts_count=F("attempts_count") + 1,
        failure_detail="",
        started_at=timezone.localtime(),
        completed_at=None,
        updated_at=timezone.localtime(),
    )
    if not claimed_count:
        return None
    provider_callback = result_request.product.provider.callback
    product_callback = result_request.product.callback
    logger.info(
        f"Result request flow started: result_request_id={result_request.pk} "
        f"provider_callback={provider_callback} "
        f"product_callback={product_callback}"
    )
    handler = get_result_fetch_handler(
        provider_callback,
        product_callback,
    )
    if not handler:
        error_message = "Result fetching is not supported for this product."
        mark_result_request_failed(result_request.pk, error_message)
        update_program_service_fetch_counts(result_request.program_service.pk)
        logger.error(
            f"Result request failed: result_request_id={result_request.pk} "
            f"error={error_message}"
        )
        logger.info(
            f"Result request flow ended: result_request_id={result_request.pk} "
            f"provider_callback={provider_callback} "
            f"product_callback={product_callback}"
        )
        return None

    provider_api_data = result_request.product.provider.api.data or {}
    logger.info(
        f"Result request handler started: result_request_id={result_request.pk} "
        f"provider_callback={provider_callback} "
        f"product_callback={product_callback}"
    )
    handler(result_request, provider_api_data)
    update_program_service_fetch_counts(result_request.program_service.pk)
    logger.info(
        f"Result request handler ended: result_request_id={result_request.pk} "
        f"provider_callback={provider_callback} "
        f"product_callback={product_callback}"
    )
    logger.info(
        f"Result request flow ended: result_request_id={result_request.pk} "
        f"provider_callback={provider_callback} "
        f"product_callback={product_callback}"
    )
    return None


class ResultRequestThread(threading.Thread):
    def __init__(self, result_request):
        super().__init__()
        self.result_request_identifier = str(result_request)

    def run(self):
        try:
            close_old_connections()
            result_request = (
                ResultRequest.objects.select_related(
                    "program_service__program",
                    "product__provider__api",
                    "created_by",
                )
                .filter(pk=self.result_request_identifier)
                .first()
            )
            if not result_request:
                return

            logger.info(
                f"Result request thread started: "
                f"result_request_id={result_request.pk}"
            )
            try:
                handle_result_request(result_request)
            except Exception as e:
                logger.exception(
                    f"Result request flow encountered an internal error: "
                    f"result_request_id={result_request.pk}",
                    exc_info=e
                )
                mark_result_request_failed(
                    result_request.pk,
                    "An internal error occurred while fetching this result.",
                )
                update_program_service_fetch_counts(
                    result_request.program_service.pk
                )
                logger.info(
                    f"Result request flow ended: "
                    f"result_request_id={result_request.pk} "
                    f"outcome={ResultRequestStatus.FAILED}"
                )
            else:
                logger.info(
                    f"Result request thread completed without internal errors: "
                    f"result_request_id={result_request.pk}"
                )
        finally:
            close_old_connections()


def start_result_request_task(result_request):
    return ResultRequestThread(result_request).start()
