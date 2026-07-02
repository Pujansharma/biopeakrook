"""Input validation for the preconsultation public APIs.

Raises `ValueError` with a readable message on malformed input, so callers get a
clear error instead of a raw `KeyError` from deep inside salience/extraction.
`client_id` (inside `client_details`) is mandatory for both capabilities.
"""

from __future__ import annotations

# Top-level keys the v3 salience layer indexes directly (would raise KeyError).
_SUMMARY_REQUIRED_KEYS = (
    "patient_baseline",
    "concerns",
    "medical_history",
    "cluster_scores",
    "health_goals",
    "lifestyle_answers",
)


def validate_summary_input(client_details: dict) -> None:
    """Validate the v3 pre-consultation form passed to (a)summarize_patient.

    Raises ValueError if client_details is not a dict, is missing a required
    top-level key, or lacks a patient_baseline.id (the trace/client id).
    """
    if not isinstance(client_details, dict):
        raise ValueError(
            f"client_details must be a dict, got {type(client_details).__name__}"
        )
    missing = [k for k in _SUMMARY_REQUIRED_KEYS if k not in client_details]
    if missing:
        raise ValueError(
            f"client_details is missing required key(s): {', '.join(missing)}"
        )
    baseline = client_details.get("patient_baseline")
    if not isinstance(baseline, dict) or not baseline.get("id"):
        raise ValueError(
            "client_details['patient_baseline'] must include a non-empty 'id'"
        )


def validate_extract_input(
    filepath: str | None,
    filebytestream: bytes | None,
    filename: str | None,
    metadata: dict | None,
    client_details: dict | None,
) -> None:
    """Validate the arguments passed to (a)extract_insights / batch entries.

    Raises ValueError if no byte source is given, the file type can't be
    determined, metadata lacks a doc_id, or client_details lacks a client_id.
    """
    if filepath is None and filebytestream is None:
        raise ValueError(
            "at least one of filepath or filebytestream must be provided"
        )
    if filepath is None and not filename:
        raise ValueError(
            "filename is required when filepath is not provided "
            "(needed to detect the file type)"
        )
    if not isinstance(metadata, dict):
        raise ValueError(
            f"metadata must be a dict, got {type(metadata).__name__}"
        )
    if not metadata.get("doc_id"):
        raise ValueError("metadata must include a non-empty 'doc_id'")
    if not isinstance(client_details, dict):
        raise ValueError(
            f"client_details must be a dict, got {type(client_details).__name__}"
        )
    _require_client_id(client_details)


def validate_extract_identity(metadata: dict | None, client_details: dict | None) -> None:
    """Validate only doc_id + client_id (used on the mock path, which reads no file)."""
    if not isinstance(metadata, dict):
        raise ValueError(
            f"metadata must be a dict, got {type(metadata).__name__}"
        )
    if not metadata.get("doc_id"):
        raise ValueError("metadata must include a non-empty 'doc_id'")
    if not isinstance(client_details, dict):
        raise ValueError(
            f"client_details must be a dict, got {type(client_details).__name__}"
        )
    _require_client_id(client_details)


def _require_client_id(client_details: dict) -> None:
    """Raise ValueError unless client_details carries a non-empty client_id."""
    if not client_details.get("client_id"):
        raise ValueError("client_details must include a non-empty 'client_id'")
