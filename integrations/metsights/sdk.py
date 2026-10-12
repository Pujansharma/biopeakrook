import io

import requests
from django.conf import settings

from accounts.users.utils.constants import Gender
from core.utils.log import logger

METSIGHTS_BASE_URL = getattr(settings, "METSIGHTS_BASE_URL", "https://api.metsights.com")

METSIGHTS_API_KEY = getattr(settings, "METSIGHTS_API_KEY", None)
METSIGHTS_REQUEST_ERROR = "MetSights request failed."


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


def get_profile_reports(
        profile_id: str, subscription_id: str, api_key: str
):
    url = METSIGHTS_BASE_URL + f"/external/profiles/{profile_id}/reports/"
    session = Session(api_key)
    response = session.get(url, params={"subscription": subscription_id})
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_metsights_report(report_id: str, api_key: str):
    url = (
            METSIGHTS_BASE_URL
            + f"/external/reports/metsights-precision/{report_id}/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_files_for_report(report_id: str, api_key: str):
    url = (
            METSIGHTS_BASE_URL
            + f"/external/reports/metsights-precision/{report_id}/files/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_trends_for_report(report_id: str, api_key: str):
    url = (
            METSIGHTS_BASE_URL
            + f"/external/reports/metsights-precision/{report_id}/trends/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_health_risk_landscape_report(report_id: str, api_key: str):
    url = METSIGHTS_BASE_URL + (
        f"/external/reports/metsights-precision/{report_id}/"
        f"health-risk-landscape/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_lifestyle_blueprint_report(report_id: str, api_key: str):
    url = METSIGHTS_BASE_URL + (
        f"/external/reports/metsights-precision/{report_id}/"
        f"lifestyle-blueprint/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_supplement_blueprint_report(report_id: str, api_key: str):
    url = METSIGHTS_BASE_URL + (
        f"/external/reports/metsights-precision/{report_id}/"
        f"supplement-blueprint/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_consolidated_precision_report(report_id: str, api_key: str):
    url = METSIGHTS_BASE_URL + (
        f"/external/reports/metsights-precision/{report_id}/"
        f"consolidated/"
    )

    session = Session(api_key)
    response = session.get(url)
    response_json = response.json()

    if not response.ok:
        detail = response_json.get("detail") or METSIGHTS_REQUEST_ERROR
        return None, detail
    data = response_json["data"]
    return data, None


def get_metsights_report_file(file_url: str):
    logger.info("MetSights report file download started")
    response = requests.get(file_url)
    if not response.ok:
        error_message = "Unable to download the MetSights report file"
        logger.error(
            f"MetSights report file download failed: "
            f"status={response.status_code}"
        )
        return None, error_message

    if not response.content:
        error_message = "MetSights returned an empty report file"
        logger.warning("MetSights report file download returned empty content")
        return None, error_message

    logger.info("MetSights report file download completed")
    return io.BytesIO(response.content), None
