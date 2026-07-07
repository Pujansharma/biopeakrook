import requests
from django.conf import settings

from core.utils.log import logger

METSIGHTS_BASE_URL = getattr(settings, 'METSIGHTS_BASE_URL', "https://api.metsights.com/")

METSIGHTS_API_KEY = getattr(settings, "METSIGHTS_API_KEY", None)


class Session(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers.update({
            'X-API-KEY': METSIGHTS_API_KEY or ""
        })


def get_metsights_profile(phone):
    url = METSIGHTS_BASE_URL + "profiles/"
    session = Session()
    response = session.get(url, params={
        'search': phone,
        'limit': 1
    })
    if not response:
        logger.warning(f'Invalid response returned, {response.status_code}: {response.json()}')
        return None
    response_data = response.json()
    data = response_data.get('data')
    if not data:
        logger.warning("No profiles exist")
        return None
    return data


def create_metsights_profile(
        phone, email, first_name, last_name, gender, age, date_of_birth
):
    profile_data = get_metsights_profile(phone)
    if profile_data:
        _profile_id = profile_data.get('id')
        return _profile_id
    url = METSIGHTS_BASE_URL + "profiles/"
    session = Session()
    payload = {
        'phone': phone,
        'email': email,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "age": age,
        "date_of_birth": date_of_birth,
    }
    response = session.post(url, json=payload)
    if not response.ok:
        logger.warning(f"Invalid response received, {response.status_code}: {response.json()}")
        return None
    _response_data = response.json()
    return _response_data
