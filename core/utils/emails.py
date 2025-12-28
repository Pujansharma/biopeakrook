import threading

from django.core.mail import EmailMessage, EmailMultiAlternatives


class EmailThread(threading.Thread):
    def __init__(self, email_message):
        self.email_message = email_message
        threading.Thread.__init__(self)

    def run(self):
        self.email_message.send()


def send_email(data):
    email_message = EmailMessage(
        subject=data['email_subject'], body=data['email_body'], to=[data['to_email']]
    )
    EmailThread(email_message).start()


def send_templated_email(subject, template, email):
    email_message = EmailMultiAlternatives(subject=subject, to=[email])
    email_message.attach_alternative(template, "text/html")
    EmailThread(email_message).start()
