import io

import requests

from core.utils.log import logger

BUGSPEAKS_BASE_URL = "https://partners.bugspeaks.com/"


class Session(requests.Session):
    def __init__(self, api_key):
        super().__init__()
        self.headers.update({
            'Authorization': 'Bearer ' + api_key,
            "User-Agent": "Biopeak-Nexus-Dev/1.0"
        })


def get_bugspeaks_record(api_key, bugspeaks_id: str):
    """
    Single Sample Search
    Args:
        api_key:
        bugspeaks_id:

    Returns:

    """
    session = Session(api_key)
    response = session.get(
        BUGSPEAKS_BASE_URL + "BPK/api/records/",
        params={
            'bugspeaks_id': bugspeaks_id
        }
    )
    if not response.ok:
        logger.warning(
            "get_bugspeaks_record failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None, "Failed to fetch"
    return response.json(), None


def _get_bugspeaks_file(api_key, bugspeaks_id: str):
    session = Session(api_key)
    response = session.get(
        BUGSPEAKS_BASE_URL + "BPK/BPK_Download_Report_API",
        params={
            'Bugspeaks_ID': bugspeaks_id
        },
        stream=True
    )
    if not response.ok:
        logger.warning(
            "get_bugspeaks_file failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    content = response.content
    _file = io.BytesIO(content)
    return _file


def _get_bugspeaks_additional_file(api_key, bugspeaks_id):
    session = Session(api_key)
    response = session.get(
        BUGSPEAKS_BASE_URL + "BPK/BPK_Additional_Report_API",
        params={
            'Bugspeaks_ID': bugspeaks_id
        },
        stream=True
    )
    if not response.ok:
        logger.warning(
            "get_bugspeaks_additional_file failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    content = response.content
    _file = io.BytesIO(content)
    return _file


def fetch_bugspeaks_report(api_key, bugspeaks_id):
    report_file = _get_bugspeaks_file(api_key, bugspeaks_id)
    if not report_file:
        return (None, None), "Failed to fetch report file"
    additional_file = _get_bugspeaks_additional_file(api_key, bugspeaks_id)
    if not additional_file:
        return (None, None), "Failed to fetch additional report file"
    return (report_file, additional_file), None


def register_bugspeaks_client(
        api_key: str,
        bugspeaks_id: str,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        address: str,
        pincode: str,
        test_type: str = "GMT"
):
    session = Session(api_key)
    url = BUGSPEAKS_BASE_URL + "BPK/api/client-kit-assignment/"
    response = session.post(
        url, json={
            "data": {
                "data": {
                    "Bugspeaks_ID": bugspeaks_id,
                    "First_Name": first_name,
                    "Last_Name": last_name,
                    "Email_ID": "-",
                    "Mobile_No": phone,
                    "Address": address,
                    "Pincode": pincode,
                    "Test_Type": test_type,
                }
            }
        }
    )
    data = response.json()
    if not response.ok:
        logger.warning(
            "register_bugspeaks_client failed: "
            f"reason=invalid_response email={email} phone={phone} "
            f"test_type={test_type} status={response.status_code} "
            f"response={response.text}"
        )
        return None, data
    return data, None


def request_sample_pickup(api_key, bugspeaks_id):
    session = Session(api_key)
    url = BUGSPEAKS_BASE_URL + "BPK/api/initiate-pickup/"
    response = session.post(
        url, json={
            "Bugspeaks_ID": bugspeaks_id
        }
    )
    if not response.ok:
        logger.warning(
            "request_sample_pickup failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    return response.json()


def submit_questionnaire(
        api_key,
        bugspeaks_id,
        age,
        gender,
        height,
        weight,
        diet_type,
        consumes_alcohol,
        alcohol_other,
        smoking,
        smoking_other,
        exercise,
        exercise_other,
        major_illness,
        illness_other,
        drugs,
        drugs_other,
        meal_type,
):
    session = Session(api_key)
    url = BUGSPEAKS_BASE_URL + "BPK/api/questionnaire/"
    _major_illness_string = "None"
    if major_illness:
        _major_illness_string = ",".join(major_illness)
    payload = {
        "Bugspeaks_ID": bugspeaks_id,
        "Test_For": "Self",
        "Test_For_Relationship": "",
        "Age": int(age),
        "Gender": gender,
        "Gender_Textbox": "",
        "Height_In_Feet": height,
        "Weight_In_KG": weight,
        "Regular_Diet": diet_type,
        "Alcoholic_Beverage": consumes_alcohol,
        "Alcoholic_Beverage_Textbox": alcohol_other or "",
        "Smoke_Tobacco": smoking,
        "Smoke_Tobacco_Textbox": smoking_other or "",
        "Exercise_Time": exercise,
        "Exercise_Time_Textbox": exercise_other or "",
        "Major_Illness": _major_illness_string,
        "Major_Illness_Textbox": illness_other or "",
        "Drug": drugs,
        "Drug_Textbox": drugs_other or "",
        "Meal_Type": meal_type,
    }
    response = session.post(url, json=payload)
    if not response.ok:
        logger.warning(
            "submit_questionnaire failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    return response.json()


def update_questionnaire(
        api_key,
        bugspeaks_id,
        age,
        gender,
        height,
        weight,
        diet_type,
        consumes_alcohol,
        alcohol_other,
        smoking,
        smoking_other,
        exercise,
        exercise_other,
        major_illness,
        illness_other,
        drugs,
        drugs_other,
        meal_type,
):
    session = Session(api_key)
    url = BUGSPEAKS_BASE_URL + "BPK/api/update-questionnaire/"
    _major_illness_string = "None"
    if major_illness:
        _major_illness_string = ",".join(major_illness)
    payload = {
        "Bugspeaks_ID": bugspeaks_id,
        "Test_For": "Self",
        "Test_For_Relationship": "",
        "Age": int(age),
        "Gender": gender,
        "Gender_Textbox": "",
        "Height_In_Feet": height,
        "Weight_In_KG": weight,
        "Regular_Diet": diet_type,
        "Alcoholic_Beverage": consumes_alcohol,
        "Alcoholic_Beverage_Textbox": alcohol_other or "",
        "Smoke_Tobacco": smoking,
        "Smoke_Tobacco_Textbox": smoking_other or "",
        "Exercise_Time": exercise,
        "Exercise_Time_Textbox": exercise_other or "",
        "Major_Illness": _major_illness_string,
        "Major_Illness_Textbox": illness_other or "",
        "Drug": drugs,
        "Drug_Textbox": drugs_other or "",
        "Meal_Type": meal_type,
    }
    response = session.post(url, json=payload)
    if not response.ok:
        logger.warning(
            "submit_questionnaire failed: "
            f"reason=invalid_response bugspeaks_id={bugspeaks_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    return response.json()
