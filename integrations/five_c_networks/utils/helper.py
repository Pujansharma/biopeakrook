from core.utils.log import logger
from integrations.five_c_networks.sdk import (
    get_access_token,
    get_pdf_report,
    get_pdf_status,
)


def process_evo_report_fetch(
        client_id: str,
        client_secret: str,
        center_id: str,
        email: str
):
    """Fetch and normalize one EVO 360 PDF report."""
    empty_files = (None,)
    logger.info(
        f"EVO 360 report fetch started: center_id={center_id}"
    )

    access_token, error = get_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )
    if error:
        logger.error(
            f"EVO 360 report fetch authentication failed: "
            f"center_id={center_id} error={error}"
        )
        return None, empty_files, error

    status_data, error = get_pdf_status(
        access_token=access_token,
        email=email,
        center_id=center_id,
    )
    if error:
        logger.error(
            f"EVO 360 report status fetch failed: "
            f"center_id={center_id} error={error}"
        )
        return None, empty_files, error

    if not isinstance(status_data, dict):
        error_message = "EVO 360 returned an invalid report status"
        logger.error(
            f"EVO 360 report status was invalid: center_id={center_id}"
        )
        return None, empty_files, error_message

    report_status = (
        status_data.get("status") or ""
    ).strip().lower()
    metadata = {
        "status": report_status,
    }

    if report_status == "processing":
        error_message = "The EVO 360 report is still processing"
        logger.warning(
            f"EVO 360 report fetch skipped: reason=report_processing "
            f"center_id={center_id}"
        )
        return metadata, empty_files, error_message

    if report_status != "found":
        error_message = "EVO 360 returned an unsupported report status"
        logger.warning(
            f"EVO 360 report fetch skipped: reason=unsupported_status "
            f"center_id={center_id} status={report_status!r}"
        )
        return metadata, empty_files, error_message

    pdf_url = status_data.get("pdf_url")
    if not pdf_url:
        error_message = "EVO 360 did not provide a PDF URL"
        logger.warning(
            f"EVO 360 report fetch skipped: reason=missing_pdf_url "
            f"center_id={center_id}"
        )
        return metadata, empty_files, error_message

    pdf_report, error = get_pdf_report(pdf_url=pdf_url)
    if error:
        logger.error(
            f"EVO 360 report download failed: "
            f"center_id={center_id} error={error}"
        )
        return metadata, empty_files, error

    logger.info(
        f"EVO 360 report fetch completed: center_id={center_id}"
    )
    return metadata, (pdf_report,), None
