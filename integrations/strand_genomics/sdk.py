import json

import arrow
import requests
from django.core.cache import cache
from requests import Session as DefaultSession

from accounts.users.models import Gender
from accounts.utils.helper import get_age_from_date_of_birth
from core.utils.log import logger

BASE_URL = "https://ghi-report-api.mystrand.org/api/external/v1"


class Session(DefaultSession):
    """Authenticated HTTP session for the Strand Genomics External API.

    Extends the default requests Session by automatically injecting the
    configured API key into every request header. A warning is emitted at
    construction time if the key is absent so misconfiguration is caught early.
    """

    def __init__(self, api_key):
        super().__init__()
        self.headers.update({
            "X-API-KEY": api_key
        })


def get_order_status(request_id, api_key):
    """Retrieve the current processing status and metadata for a genomic test order.

    Calls the ``/order-status/{trid}`` endpoint and returns a list containing
    the order record. The ``Status`` field indicates whether the order is still
    being processed or is ready for report retrieval.

    Args:
        api_key:
        request_id (str): The Test Request ID (TRID) assigned to the order.

    Returns:
        list[dict] | None: A list with a single order status object on success,
        or ``None`` if the request failed.
    """
    url = BASE_URL + f"/order-status/{request_id}"
    logger.info(f"Fetching order status for request_id={request_id}")
    session = Session(api_key)
    response = session.get(url)
    if not response.ok:
        logger.error(
            f"Failed to fetch order status for request_id={request_id} "
            f"[status={response.status_code}]: {response.text}"
        )
        return None
    logger.info(f"Successfully fetched order status for request_id={request_id}")
    return response.json()


def get_order_qc_metrics(request_id, api_key):
    """Retrieve Quality Control metrics for a processed genomic sample.

    Calls the ``/qc-metrics/{trid}`` endpoint. The returned metrics describe
    sequencing quality, including read depth, alignment rate, base quality
    scores, and total data generated.

    Args:
        api_key:
        request_id (str): The Test Request ID (TRID) of the processed sample.

    Returns:
        dict | None: A dictionary containing QC metric tags keyed by sample ID
        on success, or ``None`` if the request failed.
    """
    url = BASE_URL + f"/qc-metrics/{request_id}"
    logger.info(f"Fetching QC metrics for request_id={request_id}")
    session = Session(api_key)
    response = session.get(url)
    if not response.ok:
        logger.error(
            f"Failed to fetch QC metrics for request_id={request_id} "
            f"[status={response.status_code}]: {response.text}"
        )
        return None
    logger.info(f"Successfully fetched QC metrics for request_id={request_id}")
    return response.json()


def get_report_data(request_id, api_key):
    """Retrieve the structured JSON report for a completed genomic test.

    Calls the ``/json-report/{trid}`` endpoint. The report includes demographic
    information, personalised genomic statistics, special notes, and a detailed
    findings section covering all analysed traits and variants.

    Args:
        api_key:
        request_id (str): The Test Request ID (TRID) of the completed report.

    Returns:
        dict | None: A dictionary containing the full report payload under the
        ``report`` key on success, or ``None`` if the request failed.
    """
    url = BASE_URL + f"/json-report/{request_id}"
    logger.info(f"Fetching JSON report data for request_id={request_id}")
    session = Session(api_key)
    response = session.get(url)
    if not response.ok:
        logger.error(
            f"Failed to fetch report data for request_id={request_id} "
            f"[status={response.status_code}]: {response.text}"
        )
        return None
    logger.info(f"Successfully fetched JSON report data for request_id={request_id}")
    return response.json()


def get_vcf_file(request_id, api_key):
    """Download the raw Variant Call Format (VCF) file for a genomic sample.

    Calls the ``/vcf-file/{trid}`` endpoint and streams the response to avoid
    loading the entire file into memory at once. The returned bytes can be
    written directly to disk or passed to a bioinformatic pipeline.

    Args:
        api_key:
        request_id (str): The Test Request ID (TRID) of the sample.

    Returns:
        bytes | None: The raw VCF file content as bytes on success,
        or ``None`` if the request failed.
    """
    url = BASE_URL + f"/vcf-file/{request_id}"
    logger.info(f"Fetching VCF file for request_id={request_id}")
    session = Session(api_key)
    response = session.get(url, stream=True)
    if not response.ok:
        logger.error(
            f"Failed to fetch VCF file for request_id={request_id} "
            f"[status={response.status_code}]: {response.text}"
        )
        return None
    logger.info(f"Successfully fetched VCF file for request_id={request_id}")
    return response.content


def get_pdf_report(request_id, api_key):
    """Download the finalized PDF report for a completed genomic test.

    Calls the ``/pdf-report/{trid}`` endpoint and streams the response to avoid
    loading the entire file into memory at once. The returned bytes represent a
    valid PDF document and can be saved to disk or served directly to a client.

    Args:
        api_key:
        request_id (str): The Test Request ID (TRID) of the completed report.

    Returns:
        bytes | None: The raw PDF file content as bytes on success,
        or ``None`` if the request failed.
    """
    url = BASE_URL + f"/pdf-report/{request_id}"
    logger.info(f"Fetching PDF report for request_id={request_id}")
    session = Session(api_key)
    response = session.get(url, stream=True)
    if not response.ok:
        logger.error(
            f"Failed to fetch PDF report for request_id={request_id} "
            f"[status={response.status_code}]: {response.text}"
        )
        return None
    logger.info(f"Successfully fetched PDF report for request_id={request_id}")
    return response.content


BOOKING_BASE_URL = "https://www.zohoapis.in/creator/custom/strandls/"
BOOKING_AUTH_URL = "https://accounts.zoho.in/oauth/v2/token"


class BookingSession(requests.Session):
    def __init__(self, access_token: str):
        super().__init__()
        self.headers.update(
            {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            }
        )


def _fetch_booking_access_token(
        client_id: str, client_secret: str, refresh_token: str
) -> dict | None:
    """Fetch a fresh Zoho access token using the configured refresh token."""
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    response = requests.post(BOOKING_AUTH_URL, params=params)
    if not response.ok:
        logger.error(
            "Failed to fetch Strand booking access token: "
            f"client_id={client_id} status={response.status_code} "
            f"response={response.text}"
        )
        return None
    return response.json()


def get_booking_access_token(
        client_id: str, client_secret: str, refresh_token: str
) -> str | None:
    """Return a cached or freshly generated Strand booking access token."""
    cache_key = f"STRAND_BOOKING_ACCESS_TOKEN_{client_id}"
    access_token = cache.get(cache_key)
    if access_token:
        return access_token

    data = _fetch_booking_access_token(client_id, client_secret, refresh_token)
    if not data:
        return None

    access_token = data.get("access_token")
    if not access_token:
        logger.error(
            "Strand booking access token response missing access_token: "
            f"client_id={client_id}"
        )
        return None

    expires_in = data.get("expires_in", 3600)
    if not isinstance(expires_in, int):
        expires_in = 3600
    cache_timeout = expires_in - 60
    if cache_timeout <= 0:
        cache_timeout = 3500
    cache.set(cache_key, access_token, cache_timeout)
    return access_token


def _convert_gender(gender: str):
    mapping = {
        Gender.MALE: 'Male',
        Gender.FEMALE: 'Female',
    }
    return mapping.get(gender, 'Other')


def _convert_date(date: str | None):
    if not date:
        return None
    return arrow.get(date, ).format("DD-MMM-YYYY")


def parse_strand_request_id(response):
    result = response.get('result', {}) or {}
    if not result:
        logger.warning(
            "Response does not contain result data, exiting."
        )
        return None
    _product_list = result.get('product_list', []) or []
    if not _product_list or not len(_product_list):
        return None
    _product = _product_list[0] or {}
    test_ref = _product.get('test_ref')
    if not test_ref:
        return None
    return test_ref


def create_booking_order(
        client_id: str,
        client_secret: str,
        refresh_token: str,
        reference_id: str,
        full_name: str,
        gender: str,
        date_of_birth,
        collection_date: str,
        logged_user_email: str,
        has_medical_consent: str,
        product_code: str,
        product_name: str,
        consent_file_url: str | None = None,
) -> dict | None:
    """Create a Biopeak order in Strand LIMS through the Zoho Creator API."""
    url = BOOKING_BASE_URL + "create_biopeak_order"
    # url = BOOKING_BASE_URL + "create_biopeak_order_dev"
    access_token = get_booking_access_token(client_id, client_secret, refresh_token)
    if not access_token:
        return None

    mr_no = f"{reference_id}_{product_code}"
    age = get_age_from_date_of_birth(date_of_birth)
    payload = {
        "mrno": mr_no,
        "patient_name": full_name,
        "patient_gender": _convert_gender(gender),
        "date_of_birth": _convert_date(date_of_birth),
        "patient_age": age,
        "sample_collection_date": _convert_date(collection_date),
        "medical_consent": has_medical_consent,
        "product_list": [{
            "test_code": f"{product_code}",
            "test_name": f"{product_name}"
        }],
        "logged_user": logged_user_email,
        "documents": [
            {
                "type": "Patient Consent",
                "url": consent_file_url
            }
        ]
    }
    session = BookingSession(access_token)
    response = session.post(url, json=payload)

    if not response.ok:
        logger.error(
            "Failed to create Strand booking order: "
            f"mr_no={mr_no} product_code={product_code} "
            f"logged_user_email={logged_user_email} "
            f"status={response.status_code} response={response.text}"
        )
        return None
    response_json = response.json()

    result = response_json.get('result', {}) or {}
    error = result.get('error_code', "")
    if error:
        logger.info(
            "Failed to create Strand booking order: "
            f"mr_no={mr_no} product_code={product_code}\n "
            f"status={response.status_code}\n"
            f"response={response.text}\n"
            f"payload: {json.dumps(payload, indent=2)}\n"
            f"ENDPOINT: {response.request.url}"
        )
        return None
    logger.info(
        "Strand booking order created successfully: "
        f"mr_no={mr_no} product_code={product_code} "
        f"logged_user_email={logged_user_email}"
    )
    return response.json()
