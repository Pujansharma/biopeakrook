# Strand Genomics Webhook Payload

This document defines the webhook payload Strand Genomics should send to Biopeak Nexus when a sample, order, QC, or report status changes.

## Payload Structure

```json
{
  "event_type": "report_available",
  "event_time": "2026-05-11T17:22:15+05:30",
  "test_request_id": "TRID-2026-45191",
  "sample_id": "TRID-2026-45191",
  "external_id": "135888000224257033",
  "status": "Report generated",
  "customer": {
    "name": "Kaarthik S. R.",
    "email": "",
    "phone": "1234455677",
    "gender": "Male",
    "date_of_birth": "1985-08-23",
    "relationship": "Self"
  },
  "test": {
    "name": "NutriDNA",
    "channel_partner": "Biopeak Wellness Private Limited_Bangalore"
  },
  "report": {
    "version": "v1",
    "generated_at": "2026-05-11T17:22:15+05:30",
    "data": {}
  },
  "file": "https://secure-download-url.example.com/report.pdf"
}
```

## Status-Only Payload

Use this structure when the report and file are not available yet.

```json
{
  "event_type": "qc_failed",
  "event_time": "2026-05-11T17:22:15+05:30",
  "test_request_id": "TRID-2026-45191",
  "sample_id": "TRID-2026-45191",
  "external_id": "135888000224257033",
  "status": "QC failed",
  "customer": {
    "name": "Kaarthik S. R.",
    "email": "",
    "phone": "1234455677",
    "gender": "Male",
    "date_of_birth": "1985-08-23",
    "relationship": "Self"
  },
  "test": {
    "name": "NutriDNA",
    "channel_partner": "Biopeak Wellness Private Limited_Bangalore"
  },
  "report": null,
  "file": null
}
```

## Root Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | string | Yes | Type of webhook event. |
| `event_time` | string | Yes | ISO 8601 timestamp when the event occurred. |
| `test_request_id` | string | Yes | Unique test request ID from Strand Genomics. |
| `sample_id` | string | Yes | Unique sample ID. Use the test request ID when there is no separate sample ID. |
| `external_id` | string | Yes | Strand Genomics record ID. |
| `status` | string | Yes | Current order, sample, QC, or report status. |
| `customer` | object | Yes | Customer identity and demographic details. |
| `test` | object | Yes | Test and channel partner details. |
| `report` | object/null | No | Full JSON report object when available. Use `null` when not available. |
| `file` | string/null | No | Direct URL to the PDF or report file. Use `null` when not available. |

## Customer Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `customer.name` | string | Yes | Customer full name. |
| `customer.email` | string | No | Customer email address, if available. |
| `customer.phone` | string | Yes | Customer phone number. E.164 format is preferred when available. |
| `customer.gender` | string | No | Customer gender. |
| `customer.date_of_birth` | string | No | Customer date of birth in `YYYY-MM-DD` format. |
| `customer.relationship` | string | No | Relationship to the primary customer, such as `Self`, `Father`, `Mother`, or `Child`. |

## Test Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `test.name` | string | Yes | Name of the test or package. |
| `test.channel_partner` | string | No | Partner, center, or channel name associated with the order. |

## Report Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `report.version` | string | No | Report version, such as `v1`. |
| `report.generated_at` | string | No | ISO 8601 timestamp when the report was generated. |
| `report.data` | object | Yes, if `report` exists | Full structured JSON report data. |

## Recommended Event Types

```text
order_created
sample_collected
sample_received
qc_started
qc_failed
qc_passed
report_generated
report_available
report_revised
order_cancelled
```

## Integration Notes

- Send the full structured JSON report inside `report.data` when the report is available.
- Do not send binary PDF contents inside the webhook payload.
- Send the PDF or report file URL directly in the `file` field.
- Use `report: null` when JSON report data is not available.
- Use `file: null` when no report file URL is available.
- Use ISO 8601 timestamps for all date-time fields.
- Use `YYYY-MM-DD` format for date-only fields such as `customer.date_of_birth`.
- Webhooks must be idempotent. Biopeak should be able to safely process the same webhook more than once using `event_type`, `test_request_id`, `sample_id`, and `external_id`.
