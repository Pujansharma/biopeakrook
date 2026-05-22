from django.template.loader import get_template

from core.utils.emails import send_templated_email


def get_password_reset_template(reset_link):
    return get_template("mails/password_reset_email.html").render(
        {"reset_link": reset_link}
    )


def get_password_reset_complete_template():
    return get_template("mails/password-reset-complete.html").render()


def get_password_create_template(create_password_link):
    return get_template("mails/password_create_email.html").render(
        {"link": create_password_link}
    )


def send_reset_password_email(email, reset_link):
    template = get_password_reset_template(reset_link)
    subject = "Reset your password"
    send_templated_email(subject, template, email)


def send_password_reset_complete_email(email):
    template = get_password_reset_complete_template()
    subject = "Password reset complete"
    send_templated_email(subject, template, email)


def send_password_create_email(email, create_password_link):
    template = get_password_create_template(create_password_link)
    subject = "Create your password"
    send_templated_email(subject, template, email)
