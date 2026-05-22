from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from accounts.utils.emails import send_password_create_email
from accounts.verifications.models import (
    PhoneVerification,
    RegistrationCode,
    TOTPSession,
    TOTPCredential,
)
from accounts.verifications.utils import (
    get_secret,
    get_counter,
    get_code,
    get_expiry,
    code_valid,
    generate_secret_code,
    generate_expiry,
    get_totp_expiry,
)
from accounts.verifications.utils.emails import (
    send_verification_phone_email,
)
from accounts.verifications.utils.sms import send_login_otp_sms
from accounts.verifications.utils.whatsapp import send_verification_code_whatsapp
from core.utils.log import logger

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
        logger.info(f"OTP FOR {phone} --> {code}")
        return None

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
            "code": generate_secret_code(),
            "expires_at": generate_expiry(),
            "is_active": True,
        },
    )
    return instance


def get_registration_code(code) -> RegistrationCode | None:
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
    send_password_create_email(user.email, create_password_link)



def generate_totp_session(user) -> TOTPSession:
    session, _ = TOTPSession.objects.update_or_create(
        user=user,
        defaults={
            "token": generate_secret_code(),
            "expires_at": get_totp_expiry(),
            "is_active": True,
        },
    )
    return session


LOCKOUT_SCHEDULE = {
    10: timedelta(hours=1),
    11: timedelta(hours=2),
    12: timedelta(hours=3),
    13: timedelta(hours=6),
    14: timedelta(hours=8),
    15: timedelta(hours=12),
    16: timedelta(hours=24),
}


def apply_totp_lockout(totp_instance: TOTPCredential):
    is_permanently_locked = False
    lock_expires_at = None
    new_attempts = totp_instance.failed_attempts + 1
    if new_attempts >= 17:
        is_permanently_locked = True

    lockout_map = LOCKOUT_SCHEDULE.get(new_attempts, None)
    if lockout_map:
        lock_expires_at = timezone.now() + lockout_map

    fields = {
        "failed_attempts": F("failed_attempts") + 1,
        "lock_expires_at": lock_expires_at,
        "is_permanently_locked": is_permanently_locked,
    }

    for key, value in fields.items():
        setattr(totp_instance, key, value)

    totp_instance.save(update_fields=["updated_at", *fields.keys()])
    return totp_instance
