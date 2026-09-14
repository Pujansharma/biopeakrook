import arrow

from core.utils.log import logger
from integrations.bugspeaks.sdk import get_bugspeaks_record, fetch_bugspeaks_report


def process_bugspeaks_report_fetch(
        api_key: str, bugspeaks_id: str
):
    """Retrieve and normalize a BugSpeaks report through the SDK layer.

    This function is the reference flow for model-free provider integration
    helpers. It coordinates SDK calls, validates the provider response, and
    converts provider metadata into application-ready Python values. It does
    not access Django models, persist files, update request statuses, or
    maintain counters; those responsibilities belong to the result handler.

    Expected provider failures are returned as an error message. Unexpected
    SDK or metadata-parsing exceptions propagate to the caller.

    Args:
        api_key: Credential used by the BugSpeaks SDK requests.
        bugspeaks_id: Provider identifier for the requested report.

    Returns:
        A three-item tuple containing normalized metadata, a collection of file
        streams, and an error message. For BugSpeaks, the files are the PDF
        report and additional report in that order. Other provider helpers may
        return one, two, or any number of files through the same contract. On
        success, the error is ``None``. Expected failures return the available
        metadata, placeholder file values, and an error message.
    """
    result, error = get_bugspeaks_record(api_key, bugspeaks_id)
    if error:
        logger.error(f"Failed to retrieve bugspeaks report: {error}")
        return None, (None, None), f"Failed to retrieve bugspeaks report: {error}"

    result_status = result.get('status', "").lower() or ""
    if not result_status == "success":
        logger.error("Result data is not success")
        return None, (None, None), "Bugspeaks ID does not exist or invalid"

    result_data = result.get('data', []) or []
    if not result_data:
        return None, (None, None), "No data received"
    _item = result_data[0] or {}
    sample_pickup_details = _item.get('sample_pickup') or {}
    report_details = _item.get('report_details') or {}
    qc_details = _item.get('qc_details') or {}

    metadata = {
        "sample_pickup_date": arrow.get(sample_pickup_details.get('sample_pickup_date')).date(),
        "project_completed_timestamp": arrow.get(report_details.get('project_completed_timestamp')).date(),
        "sample_qc": qc_details.get('sample_qc'),
        "reseller_name": _item.get('reseller_name')
    }

    reports, error = fetch_bugspeaks_report(api_key, bugspeaks_id)
    if error:
        logger.error("Failed to fetch reports")
        return metadata, (None, None), "Failed to fetch files for bugspeaks report"
    return metadata, reports, None
