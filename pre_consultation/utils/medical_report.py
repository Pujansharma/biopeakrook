"""Medical report upload validation and S3 key generation."""

import os
import uuid

from django.core.exceptions import ValidationError

MEDICAL_REPORT_MAX_COUNT = 10
MEDICAL_REPORT_MAX_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_MEDICAL_REPORT_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    }
)

ALLOWED_MEDICAL_REPORT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".heic",
        ".heif",
        ".webp",
    }
)

BLOCKED_MEDICAL_REPORT_EXTENSIONS = frozenset(
    {
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".bz2",
        ".xz",
        ".tgz",
        ".tbz",
    }
)

BLOCKED_MEDICAL_REPORT_CONTENT_TYPES = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/x-tar",
        "application/gzip",
        "application/x-gzip",
        "application/x-rar-compressed",
        "application/x-7z-compressed",
        "application/x-bzip2",
        "application/x-xz",
    }
)

CONTENT_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".webp": "image/webp",
}


def sanitize_medical_report_filename(filename: str) -> str:
    base_name = os.path.basename(filename).strip()
    if not base_name or base_name in {".", ".."}:
        raise ValidationError("Invalid filename.")
    return base_name


def resolve_medical_report_extension(filename: str) -> str:
    _, extension = os.path.splitext(filename.lower())
    return extension


def resolve_medical_report_content_type(
    filename: str, declared_content_type: str
) -> str:
    extension = resolve_medical_report_extension(filename)
    if declared_content_type in ALLOWED_MEDICAL_REPORT_CONTENT_TYPES:
        return declared_content_type
    if extension in CONTENT_TYPE_BY_EXTENSION:
        return CONTENT_TYPE_BY_EXTENSION[extension]
    return declared_content_type


def validate_medical_report_upload(
    filename: str, content_type: str, size_bytes: int
) -> str:
    if size_bytes <= 0:
        raise ValidationError("Uploaded file is empty.")

    if size_bytes > MEDICAL_REPORT_MAX_SIZE_BYTES:
        raise ValidationError("Medical report must be 10 MB or smaller.")

    sanitized_filename = sanitize_medical_report_filename(filename)
    extension = resolve_medical_report_extension(sanitized_filename)

    if extension in BLOCKED_MEDICAL_REPORT_EXTENSIONS:
        raise ValidationError("Archive files are not allowed.")

    if extension not in ALLOWED_MEDICAL_REPORT_EXTENSIONS:
        raise ValidationError("Unsupported medical report file type.")

    resolved_content_type = resolve_medical_report_content_type(
        sanitized_filename,
        content_type,
    )
    if resolved_content_type in BLOCKED_MEDICAL_REPORT_CONTENT_TYPES:
        raise ValidationError("Archive files are not allowed.")

    if resolved_content_type not in ALLOWED_MEDICAL_REPORT_CONTENT_TYPES:
        raise ValidationError("Unsupported medical report file type.")

    return resolved_content_type


def medical_report_upload_to(instance, filename: str) -> str:
    sanitized_filename = sanitize_medical_report_filename(filename)
    session_id = instance.medical_history.session_id
    unique_name = f"{uuid.uuid7()}_{sanitized_filename}"
    return f"pre_consultation/medical_reports/{session_id}/{unique_name}"
