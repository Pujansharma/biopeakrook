REPORT_EVENTS = (
    "test.completed_sent",
    "order.completed",
)


def extract_event_type(body):
    event_type = body.get("event")
    if event_type:
        return str(event_type)
    return "unknown"


def extract_city_request_id(body):
    inner_payload = body.get("payload")
    if not isinstance(inner_payload, dict):
        return None

    request_data = inner_payload.get("request")
    if isinstance(request_data, dict):
        city_request_id = request_data.get("city_request_id")
        if city_request_id:
            return str(city_request_id)

    order_data = inner_payload.get("order")
    if isinstance(order_data, dict):
        city_request_id = order_data.get("city_request_id")
        if city_request_id:
            return str(city_request_id)

    return None


def extract_raw_reports(body):
    inner_payload = body.get("payload")
    if not isinstance(inner_payload, dict):
        return []
    reports = inner_payload.get("reports")
    if not isinstance(reports, list):
        return []
    return reports


def slim_report(report):
    if not isinstance(report, dict):
        return None
    report_id = report.get("id")
    if report_id is None:
        return None
    return {
        "id": report_id,
        "file_type": report.get("file_type") or "",
        "file_name": report.get("file_name") or "",
        "tokenize_public_file_url": report.get("tokenize_public_file_url") or "",
    }


def merge_reports_by_id(existing_reports, incoming_reports):
    reports_by_id = {}
    for report in existing_reports or []:
        if not isinstance(report, dict):
            continue
        report_id = report.get("id")
        if report_id is None:
            continue
        reports_by_id[report_id] = report

    for report in incoming_reports or []:
        slimmed_report = slim_report(report)
        if slimmed_report is None:
            continue
        reports_by_id[slimmed_report["id"]] = slimmed_report

    return list(reports_by_id.values())
