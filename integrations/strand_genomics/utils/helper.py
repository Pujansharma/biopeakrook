from core.utils.log import logger
from integrations.strand_genomics.sdk import (
    get_order_status,
    get_pdf_report,
    get_report_data,
    get_vcf_file,
)


def process_strand_genomics_report_fetch(
        api_key: str, request_id: str
):
    """Fetch Strand order metadata and every available report artifact.

    Expected provider failures are returned as an error message. Unexpected
    SDK or metadata-parsing exceptions propagate to the caller.

    Args:
        api_key: Credential used by the Strand Genomics SDK requests.
        request_id: Provider identifier for the requested report.

    Returns:
        Normalized metadata, a PDF/VCF/JSON artifact tuple, and an optional
        combined error message.
    """
    empty_artifacts = (None, None, None)

    if not request_id:
        error_message = "Invalid Strand request ID provided"
        logger.warning(
            f"STRAND_001 Strand Genomics Result Fetch skipped: "
            f"reason=missing_request_id request_id={request_id}"
        )
        return None, empty_artifacts, error_message

    logger.info(
        f"STRAND_001 Strand Genomics Result Fetch fetching order status: "
        f"request_id={request_id}"
    )
    status_data, status_error = get_order_status(request_id, api_key=api_key)
    if status_error:
        logger.error(
            f"STRAND_001 Strand Genomics Result Fetch order status failed: "
            f"request_id={request_id} error={status_error}"
        )
        return None, empty_artifacts, status_error
    if not isinstance(status_data, list) or not status_data:
        error_message = "Strand order status did not contain a report record"
        logger.error(
            f"STRAND_001 Strand Genomics Result Fetch invalid order status: "
            f"request_id={request_id} error={error_message}"
        )
        return None, empty_artifacts, error_message

    data = status_data[0] or {}
    if not isinstance(data, dict):
        error_message = "Strand order status report record was invalid"
        logger.error(
            f"STRAND_001 Strand Genomics Result Fetch invalid report record: "
            f"request_id={request_id} error={error_message}"
        )
        return None, empty_artifacts, error_message

    logger.info(
        f"STRAND_001 Strand Genomics Result Fetch fetched order status: "
        f"request_id={request_id}"
    )

    metadata = {
        "reference_id": data.get("ID"),
        "status": data.get("Status") or "",
        "email": data.get("Email"),
        "date_of_birth": data.get("Date_of_birth"),
        "phone": data.get("Phone_Number"),
        "gender": data.get("Gender"),
        "test_name": data.get("Name_of_the_Test", "") or "",
        "partner_name": data.get("Channel_Partner"),
        "relationship": data.get("Relationship"),
        "sample_kit_id": data.get("Sample_ID"),
    }

    pdf_report, pdf_error = get_pdf_report(request_id, api_key)
    vcf_file, vcf_error = get_vcf_file(request_id, api_key)
    json_data, json_error = get_report_data(request_id, api_key)

    error_messages = [
        error_message
        for error_message in (pdf_error, vcf_error, json_error)
        if error_message
    ]
    combined_error = "; ".join(error_messages) or None
    logger.info(
        f"STRAND_001 Strand Genomics Result Fetch artifacts received: "
        f"request_id={request_id} pdf_available={pdf_report is not None} "
        f"vcf_available={vcf_file is not None} "
        f"json_available={bool(json_data)}"
    )
    if combined_error:
        logger.warning(
            f"STRAND_001 Strand Genomics Result Fetch artifacts incomplete: "
            f"request_id={request_id} error={combined_error}"
        )

    artifacts = (pdf_report, vcf_file, json_data)
    return metadata, artifacts, combined_error
