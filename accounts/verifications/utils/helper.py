from django.conf import settings
from django.db.models import F
from django.utils import timezone

from core.utils.log import logger
from ..models import PhoneVerification, RegistrationCode
from ..utils import (
    get_secret,
    get_counter,
    get_code,
    get_expiry,
    code_valid,
    generate_code,
    generate_expiry,
)
from ..utils.emails import send_create_password_email, send_verification_phone_email
from ..utils.sms import send_login_otp_sms
from ..utils.whatsapp import send_verification_code_whatsapp

PASSWORD_URL = getattr(settings, "PASSWORD_BASE_URL", "") + "/create-password?code={}"


def set_values_for_phone_verification(instance):
    data = {
        "secret": get_secret(),
        "counter": get_counter(),
        "expires_at": get_expiry(),
        "retry_count": F("retry_count") + 1,
        "is_active": True,
    }
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save(update_fields=["updated_at", *data.keys()])
    return instance


def perform_otp_generation(phone, code):
    if settings.DEBUG:
        send_verification_phone_email(phone, code)
        return logger.info(f"OTP FOR {phone} --> {code}")

    send_verification_code_whatsapp(phone, code)
    send_login_otp_sms(phone, code)
    return None


def generate_otp_for_phone(phone, purpose):
    instance, created = PhoneVerification.objects.get_or_create(
        phone=phone, purpose=purpose
    )
    otp_time_diff = (timezone.localtime() - instance.updated_at).seconds
    if not created and instance.is_active:
        if instance.retry_count % 3 < 3 and otp_time_diff < 60:
            return instance, False
        if instance.retry_count % 3 == 0 and otp_time_diff < 300:
            return instance, False
    instance = set_values_for_phone_verification(instance)
    otp_code = get_code(instance.secret, instance.counter)
    perform_otp_generation(instance.phone, otp_code)
    return instance, True


def verify_otp(instance, code):
    secret = instance.secret
    counter = instance.counter
    is_valid = code_valid(secret=secret, counter=counter, code=code)
    if is_valid:
        PhoneVerification.objects.filter(pk=instance.pk).update(
            secret=None,
            counter=0,
            retry_count=0,
            is_active=False,
        )
    return is_valid


def generate_registration_code_for_user(user):
    instance, _ = RegistrationCode.objects.update_or_create(
        user=user,
        defaults={
            "code": generate_code(),
            "expires_at": generate_expiry(),
            "is_active": True,
        },
    )
    return instance


def get_registration_code(code):
    return (
        RegistrationCode.objects.select_related("user")
        .filter_active(
            code__exact=code,
            expires_at__gte=timezone.now(),
        )
        .first()
    )


def send_registration_code(user):
    registration_code = generate_registration_code_for_user(user)
    create_password_link = PASSWORD_URL.format(registration_code.code)
    send_create_password_email(user.email, create_password_link)
