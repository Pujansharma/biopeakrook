import requests
from django.conf import settings

from accounts.users.utils.constants import Gender
from core.utils.log import logger

METSIGHTS_BASE_URL = getattr(settings, 'METSIGHTS_BASE_URL', "https://api.metsights.com")

METSIGHTS_API_KEY = getattr(settings, "METSIGHTS_API_KEY", None)


class Session(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers.update({
            'X-API-KEY': METSIGHTS_API_KEY or ""
        })


GENDER_MAPPING = {
    Gender.MALE: "1",
    Gender.FEMALE: "2"
}


def get_metsights_profile(phone):
    url = METSIGHTS_BASE_URL + "/profiles/"
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
    return data[0].get('id')


def create_metsights_profile(
        phone, email, first_name, last_name, gender, age, date_of_birth
):
    profile_id = get_metsights_profile(phone)
    if profile_id:
        return {"data": {"id": profile_id}}
    url = METSIGHTS_BASE_URL + "/profiles/"
    session = Session()
    gender_value = GENDER_MAPPING.get(gender)
    payload = {
        'phone': phone,
        'email': email,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender_value,
        "age": age,
        "date_of_birth": str(date_of_birth),
    }
    response = session.post(url, json=payload)
    if not response.ok:
        logger.warning(f"Invalid response received, {response.status_code}: {response.json()}")
        return None
    response_data = response.json()
    return response_data
