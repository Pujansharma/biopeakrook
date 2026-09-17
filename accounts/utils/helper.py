import secrets
import string
from datetime import datetime

import arrow
from django.utils import timezone


def generate_password(length=64):
    punctuation = "!#$%&()*+,-./:;<=>?@[]^_`{|}~"
    return "".join(
        secrets.choice(string.ascii_letters + string.digits + punctuation)
        for _ in range(length)
    )


def get_random_letters(length=10):
    return "".join(secrets.choice(string.ascii_letters) for _ in range(length))


def get_date_of_birth_from_age(age_input):
    calculated_year = timezone.now().year - int(age_input)
    date = datetime.strptime(f"{calculated_year}-01-01", "%Y-%m-%d").date()
    return date


def check_age_greater_than_18(date_input):
    diff = (timezone.now().date() - date_input).days // 365
    return bool(diff >= 18)


def get_split_names(full_name: str) -> tuple[str | None, str | None]:
    """Function to split full name into first_name, last_name"""
    parts = full_name.split()
    if not parts:
        return None, None
    *first_part, last_name = parts
    first_name = " ".join(first_part).title()
    if not first_name:
        first_name = last_name.title()
        last_name = None
        return first_name, last_name
    return first_name, last_name.title()


def get_age_from_date_of_birth(date_of_birth):
    if not date_of_birth:
        return None
    _date = arrow.get(date_of_birth).date()
    diff = (timezone.localdate() - _date).days // 365
    return diff


def dedupe_ids(item_ids):
    """Preserve order; drop duplicate IDs (Postgres ON CONFLICT batch safety)."""
    seen = set()
    unique_ids = []
    for item_id in item_ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_ids.append(item_id)
    return unique_ids


def dedupe_id_dicts(items):
    """Keep first dict per `id`."""
    seen = set()
    unique_items = []
    for item in items:
        item_id = item["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_items.append(item)
    return unique_items
