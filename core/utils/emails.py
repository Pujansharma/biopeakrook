import threading
from collections.abc import Iterable
from typing import NamedTuple

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives


class EmailAttachment(NamedTuple):
    filename: str
    content: bytes
    mimetype: str


class EmailThread(threading.Thread):
    def __init__(self, email_message):
        self.email_message = email_message
        threading.Thread.__init__(self)

    def run(self):
        self.email_message.send()


def send_email(data):
    email_message = EmailMessage(
        subject=data["email_subject"], body=data["email_body"], to=[data["to_email"]]
    )
    EmailThread(email_message).start()


def send_templated_email(subject, template, email):
    email_message = EmailMultiAlternatives(subject=subject, to=[email])
    email_message.attach_alternative(template, "text/html")
    EmailThread(email_message).start()


def send_templated_email_with_attachments(
    subject: str,
    template: str,
    email: str,
    attachments: Iterable[EmailAttachment],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
) -> None:
    email_message = EmailMultiAlternatives(
        subject=subject, to=[email], from_email=from_email
    )
    email_message.attach_alternative(template, "text/html")
    for attachment in attachments:
        email_message.attach(
            attachment.filename,
            attachment.content,
            attachment.mimetype,
        )
    EmailThread(email_message).start()
