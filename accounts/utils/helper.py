import secrets
import string
from datetime import datetime

from django.utils import timezone

from core.utils.helper import generate_uuid


def generate_password(length=64):
    punctuation = "!#$%&()*+,-./:;<=>?@[]^_`{|}~"
    return ''.join(secrets.choice(string.ascii_letters + string.digits + punctuation) for _ in range(length))


def get_random_letters(length=10):
    return ''.join(secrets.choice(string.ascii_letters) for _ in range(length))


def get_unique_id():
    return generate_uuid().hex[:8].upper()


def get_uuid_hex():
    return generate_uuid().hex


def get_unique_number(length=6):
    uuid = generate_uuid()
    return str(uuid.int)[:length]


def get_person_unique_id():
    return get_random_letters(2).upper() + get_unique_number()


def get_random_email():
    return str(generate_uuid().hex[:10].lower()) + "@email.com"


def get_date_of_birth_from_age(age_input):
    calculated_year = timezone.now().year - int(age_input)
    date = datetime.strptime(f'{calculated_year}-01-01', "%Y-%m-%d").date()
    return date


def check_age_greater_than_18(date_input):
    diff = (timezone.now().date() - date_input).days // 365
    return bool(diff >= 18)
