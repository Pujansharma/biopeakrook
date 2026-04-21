import secrets
import string
from datetime import datetime

from django.utils import timezone


def generate_password(length=64):
    punctuation = "!#$%&()*+,-./:;<=>?@[]^_`{|}~"
    return ''.join(secrets.choice(string.ascii_letters + string.digits + punctuation) for _ in range(length))


def get_random_letters(length=10):
    return ''.join(secrets.choice(string.ascii_letters) for _ in range(length))


def get_date_of_birth_from_age(age_input):
    calculated_year = timezone.now().year - int(age_input)
    date = datetime.strptime(f'{calculated_year}-01-01', "%Y-%m-%d").date()
    return date


def check_age_greater_than_18(date_input):
    diff = (timezone.now().date() - date_input).days // 365
    return bool(diff >= 18)
