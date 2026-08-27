import arrow

BUGSPEAKS_STATUS_CLIENT_ASSIGNED = "Client Assigned"
BUGSPEAKS_STATUS_KIT_DISPATCHED = "Kit Dispatched"
BUGSPEAKS_STATUS_KIT_DELIVERED = "Kit Delivered"
BUGSPEAKS_STATUS_REQUEST_DELAYED = "Request Delayed"
BUGSPEAKS_STATUS_PICKUP_REQUESTED = "Pick Up Requested"
BUGSPEAKS_STATUS_PICKUP_INITIATED = "Pick Up Initiated"
BUGSPEAKS_STATUS_SAMPLE_PICKED_UP = "Sample Picked Up"
BUGSPEAKS_STATUS_SAMPLE_RECEIVED = "Sample Received"
BUGSPEAKS_STATUS_QC_PASSED = "QC Passed"
BUGSPEAKS_STATUS_QC_FAILED = "QC Failed"
BUGSPEAKS_STATUS_COMPLETED = "Completed"
BUGSPEAKS_NOTE_TIMESTAMP_FORMAT = "DD MMM YYYY, hh:mm:ss A"


def parse_bugspeaks_date(value: str | None):
    """Return a date parsed from a Bugspeaks timestamp string."""
    if not value:
        return None
    try:
        return arrow.get(value).date()
    except arrow.parser.ParserError:
        return None


def get_bugspeaks_record_payload(response: dict | None) -> dict | None:
    """Return the first Bugspeaks record payload from a successful response."""
    if not isinstance(response, dict):
        return None
    if response.get("status") != "success":
        return None
    records = response.get("data")
    if not isinstance(records, list):
        return None
    if not records:
        return None
    first_record = records[0]
    if not isinstance(first_record, dict):
        return None
    return first_record


def normalize_bugspeaks_record_details(record: dict) -> dict:
    """Return normalized metadata sections from a Bugspeaks record payload."""
    customer_details = record.get("customer_details") or {}
    kit_dispatch = record.get("kit_dispatch") or {}
    sample_pickup = record.get("sample_pickup") or {}
    qc_details = record.get("qc_details") or {}
    report_details = record.get("report_details") or {}
    analysis_details = record.get("analysis_details") or {}

    provider_details = {}
    bugspeaks_id = record.get("bugspeaks_id")
    reseller_name = record.get("reseller_name")
    if bugspeaks_id:
        provider_details["bugspeaks_id"] = bugspeaks_id
    if reseller_name:
        provider_details["reseller_name"] = reseller_name
    if customer_details:
        provider_details["customer_details"] = customer_details

    kit_status = {}
    dispatch_courier_partner = kit_dispatch.get("courier_partner")
    dispatch_tracking_id = kit_dispatch.get("tracking_id")
    dispatch_date = kit_dispatch.get("dispatch_date")
    delivered_date = kit_dispatch.get("delivered_date")
    delivered_tracking_id = kit_dispatch.get("delivered_tracking_id")
    delivered_courier_partner = kit_dispatch.get("delivered_courier_partner")
    pickup_courier_partner = sample_pickup.get("courier_partner")
    pickup_tracking_id = sample_pickup.get("tracking_id")
    pickup_requested_date = sample_pickup.get("pickup_requested_date")
    pickup_initiated_date = sample_pickup.get("pickup_initiated_date")
    sample_pickup_date = sample_pickup.get("sample_pickup_date")
    sample_received_date = sample_pickup.get("sample_received_date")
    sample_pickup_tracking_id = sample_pickup.get("sample_pickup_tracking_id")
    sample_pickup_courier_partner = sample_pickup.get("sample_pickup_courier_partner")

    if dispatch_courier_partner:
        kit_status["dispatch_courier_partner"] = dispatch_courier_partner
    if dispatch_tracking_id:
        kit_status["dispatch_tracking_id"] = dispatch_tracking_id
    if dispatch_date:
        kit_status["dispatch_date"] = dispatch_date
    if delivered_date:
        kit_status["delivered_date"] = delivered_date
    if delivered_tracking_id:
        kit_status["delivered_tracking_id"] = delivered_tracking_id
    if delivered_courier_partner:
        kit_status["delivered_courier_partner"] = delivered_courier_partner
    if pickup_courier_partner:
        kit_status["pickup_courier_partner"] = pickup_courier_partner
    if pickup_tracking_id:
        kit_status["pickup_tracking_id"] = pickup_tracking_id
    if pickup_requested_date:
        kit_status["pickup_requested_date"] = pickup_requested_date
    if pickup_initiated_date:
        kit_status["pickup_initiated_date"] = pickup_initiated_date
    if sample_pickup_date:
        kit_status["sample_pickup_date"] = sample_pickup_date
    if sample_received_date:
        kit_status["sample_received_date"] = sample_received_date
    if sample_pickup_tracking_id:
        kit_status["sample_pickup_tracking_id"] = sample_pickup_tracking_id
    if sample_pickup_courier_partner:
        kit_status["sample_pickup_courier_partner"] = sample_pickup_courier_partner

    qc_status = {}
    sample_qc = qc_details.get("sample_qc")
    sample_qc_date = qc_details.get("sample_qc_date")
    sample_qc_by = qc_details.get("sample_qc_by")
    if sample_qc:
        qc_status["sample_qc"] = sample_qc
    if sample_qc_date:
        qc_status["sample_qc_date"] = sample_qc_date
    if sample_qc_by:
        qc_status["sample_qc_by"] = sample_qc_by

    report_status = {}
    report_validated_by = report_details.get("report_validated_by")
    report_validation_date = report_details.get("report_validation_date")
    project_status = report_details.get("project_status")
    project_completed_timestamp = report_details.get("project_completed_timestamp")
    if report_validated_by:
        report_status["report_validated_by"] = report_validated_by
    if report_validation_date:
        report_status["report_validation_date"] = report_validation_date
    if project_status:
        report_status["project_status"] = project_status
    if project_completed_timestamp:
        report_status["project_completed_timestamp"] = project_completed_timestamp

    analysis_status = {}
    data_analysis_start_date = analysis_details.get("data_analysis_start_date")
    data_analysis_completed_date = analysis_details.get("data_analysis_completed_date")
    data_analysis_checkpoint = analysis_details.get("data_analysis_checkpoint")
    if data_analysis_start_date:
        analysis_status["data_analysis_start_date"] = data_analysis_start_date
    if data_analysis_completed_date:
        analysis_status["data_analysis_completed_date"] = data_analysis_completed_date
    if data_analysis_checkpoint:
        analysis_status["data_analysis_checkpoint"] = data_analysis_checkpoint

    normalized = {}
    if provider_details:
        normalized["provider_details"] = provider_details
    if kit_status:
        normalized["kit_status"] = kit_status
    if qc_status:
        normalized["qc_status"] = qc_status
    if analysis_status:
        normalized["analysis_status"] = analysis_status
    if report_status:
        normalized["report_status"] = report_status
    return normalized


def normalize_bugspeaks_webhook_payload(payload: dict, project_status: str) -> dict:
    """Return normalized metadata sections from a Bugspeaks webhook payload."""
    normalized = {}
    provider_details = {}
    bugspeaks_id = payload.get("Bugspeaks_ID")
    reseller_name = payload.get("Reseller_Name")
    if bugspeaks_id:
        provider_details["bugspeaks_id"] = bugspeaks_id
    if reseller_name:
        provider_details["reseller_name"] = reseller_name

    kit_status = {}
    assigned_date = payload.get("Client_Kit_Assigned_Date")
    dispatch_courier_partner = payload.get("Courier_Partner")
    dispatch_tracking_id = payload.get("Tracking_ID")
    dispatch_date = payload.get("Dispatch_Date")
    delivered_date = payload.get("Delivered_Date")
    delivered_tracking_id = payload.get("Delivered_Tracking_ID")
    delivered_courier_partner = payload.get("Delivered_Courier_Partner")
    pickup_requested_date = payload.get("Pickup_Requested_Date")
    pickup_initiated_date = payload.get("Pickup_Initiated_Date")
    sample_pickup_date = payload.get("Sample_Pickup_Date")
    sample_received_date = payload.get("Sample_Received_Date")
    sample_pickup_tracking_id = payload.get("Sample_Pickup_Tracking_ID")
    sample_pickup_courier_partner = payload.get("Sample_Pickup_Courier_Partner")

    if assigned_date:
        kit_status["assigned_date"] = assigned_date
    if dispatch_courier_partner:
        kit_status["dispatch_courier_partner"] = dispatch_courier_partner
    if dispatch_tracking_id:
        kit_status["dispatch_tracking_id"] = dispatch_tracking_id
    if dispatch_date:
        kit_status["dispatch_date"] = dispatch_date
    if delivered_date:
        kit_status["delivered_date"] = delivered_date
    if delivered_tracking_id:
        kit_status["delivered_tracking_id"] = delivered_tracking_id
    if delivered_courier_partner:
        kit_status["delivered_courier_partner"] = delivered_courier_partner
    if pickup_requested_date:
        kit_status["pickup_requested_date"] = pickup_requested_date
    if pickup_initiated_date:
        kit_status["pickup_initiated_date"] = pickup_initiated_date
    if sample_pickup_date:
        kit_status["sample_pickup_date"] = sample_pickup_date
    if sample_received_date:
        kit_status["sample_received_date"] = sample_received_date
    if sample_pickup_tracking_id:
        kit_status["sample_pickup_tracking_id"] = sample_pickup_tracking_id
    if sample_pickup_courier_partner:
        kit_status["sample_pickup_courier_partner"] = sample_pickup_courier_partner
    if project_status:
        kit_status["latest_project_status"] = project_status

    qc_status = {}
    sample_qc = payload.get("Sample_QC")
    sample_qc_date = payload.get("Sample_QC_Date")
    sample_qc_by = payload.get("Sample_QC_By")
    if sample_qc:
        qc_status["sample_qc"] = sample_qc
    if sample_qc_date:
        qc_status["sample_qc_date"] = sample_qc_date
    if sample_qc_by:
        qc_status["sample_qc_by"] = sample_qc_by

    report_status = {}
    report_validated_by = payload.get("Report_Validated_By")
    report_validation_date = payload.get("Report_Validation_Date")
    project_completed_timestamp = payload.get("Project_Completed_Timestamp")
    if project_status:
        report_status["project_status"] = project_status
    if report_validated_by:
        report_status["report_validated_by"] = report_validated_by
    if report_validation_date:
        report_status["report_validation_date"] = report_validation_date
    if project_completed_timestamp:
        report_status["project_completed_timestamp"] = project_completed_timestamp

    if provider_details:
        normalized["provider_details"] = provider_details
    if kit_status:
        normalized["kit_status"] = kit_status
    if qc_status:
        normalized["qc_status"] = qc_status
    if report_status:
        normalized["report_status"] = report_status
    return normalized


def append_bugspeaks_note(existing_notes: str | None, note: str | None) -> str | None:
    """Append a Bugspeaks note only when it is not already present."""
    if not note:
        return existing_notes
    if not existing_notes:
        return note
    existing_note_lines = existing_notes.splitlines()
    if note in existing_note_lines:
        return existing_notes
    return f"{existing_notes}\n{note}"


def build_bugspeaks_status_note(project_status: str | None, status_data: dict) -> str:
    """Build a human-readable Bugspeaks status note."""
    if not project_status:
        return ""

    if project_status == BUGSPEAKS_STATUS_CLIENT_ASSIGNED:
        assigned_date: str | None = status_data.get("assigned_date")
        if not assigned_date:
            return "Client Assigned: Kit assigned."
        formatted_date = arrow.get(assigned_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Client Assigned: Kit assigned on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_KIT_DISPATCHED:
        dispatch_date: str | None = status_data.get("dispatch_date")
        tracking_id: str | None = status_data.get("dispatch_tracking_id")
        if not dispatch_date:
            return "Kit Dispatched: Bugspeaks kit dispatched."

        if tracking_id:
            formatted_date = arrow.get(dispatch_date).format(
                BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
            )
            return f"Kit Dispatched: Tracking ID {tracking_id} on {formatted_date}."

        formatted_date = arrow.get(dispatch_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Kit Dispatched: Kit dispatched on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_KIT_DELIVERED:
        delivered_date: str | None = status_data.get("delivered_date")
        if not delivered_date:
            return "Kit Delivered: Bugspeaks kit delivered."

        formatted_date = arrow.get(delivered_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Kit Delivered: Kit delivered on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_REQUEST_DELAYED:
        return "Request Delayed: Bugspeaks request delayed."

    if project_status == BUGSPEAKS_STATUS_PICKUP_REQUESTED:
        requested_date: str | None = status_data.get("pickup_requested_date")
        if not requested_date:
            return "Pick Up Requested: Sample pickup requested."
        formatted_date = arrow.get(requested_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Pick Up Requested: Sample pickup requested on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_PICKUP_INITIATED:
        initiated_date: str | None = status_data.get("pickup_initiated_date")
        if not initiated_date:
            return "Pick Up Initiated: Sample pickup initiated."
        formatted_date = arrow.get(initiated_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Pick Up Initiated: Sample pickup initiated on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_SAMPLE_PICKED_UP:
        pickup_date: str | None = status_data.get("sample_pickup_date")
        if not pickup_date:
            return "Sample Picked Up: Bugspeaks sample picked up."
        formatted_date = arrow.get(pickup_date).format(BUGSPEAKS_NOTE_TIMESTAMP_FORMAT)
        return f"Sample Picked Up: Sample picked up on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_SAMPLE_RECEIVED:
        received_date: str | None = status_data.get("sample_received_date")
        if not received_date:
            return "Sample Received: Bugspeaks sample received."
        formatted_date = arrow.get(received_date).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Sample Received: Sample received on {formatted_date}."

    if project_status in [BUGSPEAKS_STATUS_QC_PASSED, BUGSPEAKS_STATUS_QC_FAILED]:
        sample_qc: str | None = status_data.get("sample_qc")
        sample_qc_date: str | None = status_data.get("sample_qc_date")
        formatted_date = None
        if sample_qc_date:
            formatted_date = arrow.get(sample_qc_date).format(
                BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
            )
        if not sample_qc and not formatted_date:
            return "QC Updated: Sample QC updated."
        if sample_qc and not formatted_date:
            return f"QC Updated: Sample QC {sample_qc}."
        if formatted_date and not sample_qc:
            return f"QC Updated: Sample QC updated on {formatted_date}."
        return f"QC Updated: Sample QC {sample_qc} on {formatted_date}."

    if project_status == BUGSPEAKS_STATUS_COMPLETED:
        completed_at: str | None = status_data.get("project_completed_timestamp")
        if not completed_at:
            return "Completed: Bugspeaks report completed."
        formatted_date = arrow.get(completed_at).format(
            BUGSPEAKS_NOTE_TIMESTAMP_FORMAT
        )
        return f"Completed: Bugspeaks report completed on {formatted_date}."

    return f"{project_status}: Bugspeaks webhook received."


def get_bugspeaks_metadata_date(normalized_data: dict):
    """Return the preferred assessment date from normalized Bugspeaks data."""
    report_status = normalized_data.get("report_status") or {}
    kit_status = normalized_data.get("kit_status") or {}
    preferred_values = [
        report_status.get("project_completed_timestamp"),
        report_status.get("report_validation_date"),
        kit_status.get("sample_received_date"),
    ]
    for value in preferred_values:
        parsed_date = parse_bugspeaks_date(value)
        if parsed_date:
            return parsed_date
    return None


def get_bugspeaks_practitioner_name(normalized_data: dict) -> str | None:
    """Return the report validator name from normalized Bugspeaks data."""
    report_status = normalized_data.get("report_status") or {}
    return report_status.get("report_validated_by")
