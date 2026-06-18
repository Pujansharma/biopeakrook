import mimetypes
from collections.abc import Iterable, Iterator
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.template.loader import get_template

from core.utils.emails import EmailAttachment, send_templated_email_with_attachments

REPORTS_EXPORT_EMAIL_SUBJECT = "Your Reports Are Attached — Biopeak"
REPORTS_EXPORT_EMAIL_TEMPLATE = "mails/metsights_reports_export_email.html"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_ATTACHMENT_MIMETYPE = "application/octet-stream"


def get_report_file_name(file_payload: dict) -> str:
    file_url = file_payload.get("file_url") or ""
    return Path(urlparse(file_url).path).name


def get_report_file_mimetype(filename: str, content_type: str | None) -> str:
    guessed_mimetype = mimetypes.guess_type(filename)[0]
    return content_type or guessed_mimetype or DEFAULT_ATTACHMENT_MIMETYPE


def fetch_report_file(file_payload: dict) -> tuple[str, bytes] | None:
    file_url: str | None = file_payload.get("file_url")
    filename = get_report_file_name(file_payload)
    if not file_url or not filename:
        return None

    try:
        response = requests.get(
            file_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    return filename, response.content


def fetch_report_files(files: Iterable[dict]) -> Iterator[tuple[str, bytes]]:
    for file_payload in files:
        if isinstance(file_payload, dict) and file_payload.get("file_url"):
            attachment = fetch_report_file(file_payload)
            if attachment:
                yield attachment


def get_email_attachment(file: tuple[str, bytes]) -> EmailAttachment:
    filename, content = file
    return EmailAttachment(
        filename=filename,
        content=content,
        mimetype=get_report_file_mimetype(filename, None),
    )


def get_reports_export_email_template(subject: str, first_name: str) -> str:
    return get_template(REPORTS_EXPORT_EMAIL_TEMPLATE).render(
        {
            "subject": subject,
            "first_name": first_name
        }
    )


def send_reports_export_email(email, first_name, files) -> None:
    if not email:
        return

    subject = "Reports export"
    template = get_reports_export_email_template(subject, first_name)
    _files = fetch_report_files(files)
    attachments = [
        get_email_attachment(file) for file in _files
    ]
    if not attachments:
        return

    send_templated_email_with_attachments(
        REPORTS_EXPORT_EMAIL_SUBJECT,
        template,
        email,
        attachments,
        from_email="care@mails.biopeak.com"
    )
