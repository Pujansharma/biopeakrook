import requests
from django.conf import settings

from accounts.users.utils.constants import Gender
from core.utils.log import logger

METSIGHTS_BASE_URL = getattr(settings, 'METSIGHTS_BASE_URL', "https://api.metsights.com")

METSIGHTS_API_KEY = getattr(settings, "METSIGHTS_API_KEY", None)


class Session(requests.Session):
    def __init__(self, api_key=METSIGHTS_API_KEY):
        super().__init__()
        self.headers.update({
            'X-API-KEY': api_key or ""
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
        phone, email, first_name, last_name, gender, age=None, date_of_birth=None
):
    profile_id = get_metsights_profile(phone)
    if profile_id:
        return {"data": {"id": profile_id}}
    url = METSIGHTS_BASE_URL + "/profiles/"
    session = Session()
    gender_value = GENDER_MAPPING.get(gender)
    date_of_birth_value = None
    if date_of_birth:
        date_of_birth_value = str(date_of_birth)

    payload = {
        'phone': phone,
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender_value,
        "date_of_birth": date_of_birth_value,
    }
    if age:
        payload['age'] = age
    if email:
        payload['email'] = email
    response = session.post(url, json=payload)
    if not response.ok:
        logger.warning(f"Invalid response received, {response.status_code}: {response.json()}")
        return None
    response_data = response.json()
    return response_data


def get_trends_for_profile(profile_id, assessment_type, api_key=None):
    url = METSIGHTS_BASE_URL + f"external/profiles/{profile_id}/trends/"
    session_api_key = METSIGHTS_API_KEY
    if api_key and api_key is not None:
        session_api_key = api_key
    session = Session(session_api_key)
    _response = session.get(url, params={'assessment_type': assessment_type})
