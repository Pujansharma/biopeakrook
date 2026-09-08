from datetime import date
from decimal import Decimal
from urllib.parse import quote, unquote

from accounts.users.utils.constants import Gender


def calculate_age(date_of_birth, today=None):
    if not date_of_birth:
        return None
    reference = today or date.today()
    years = reference.year - date_of_birth.year
    birthday_passed = (reference.month, reference.day) >= (
        date_of_birth.month,
        date_of_birth.day,
    )
    if not birthday_passed:
        years -= 1
    return years


def url_encode_address(address):
    return quote(str(address or "").strip(), safe="")


def url_decode_address(address):
    return unquote(str(address or "").strip())


def profile_label(customer_profile):
    first_name = (customer_profile.first_name or "").strip()
    last_name = (customer_profile.last_name or "").strip()
    return f"{first_name} {last_name}".strip()


def profile_gender(customer_profile):
    gender_value = customer_profile.gender
    if not gender_value:
        return None
    return Gender.MAPPING.get(gender_value, customer_profile.get_gender_display())


def orange_catalog_id(value):
    return str(value).strip()


def build_orange_create_payload(address, notes, slot_datetime, customers):
    primary = customers[0]
    patient_details = []
    for customer in customers:
        tests = []
        packages = []
        for line in customer["line_snapshots"]:
            catalog_id = orange_catalog_id(line["test_id"])
            if line["is_custom_package"]:
                packages.append({"package_id": catalog_id})
            else:
                tests.append({"test_id": catalog_id})
        profile = customer["customer_profile"]
        patient_details.append(
            {
                "partner_reference_id": str(customer["user_id"]),
                "patient_name": customer["name"],
                "patient_phone": customer["phone"],
                "age": str(customer["age"]),
                "gender": Gender.MAPPING.get(
                    profile.gender, profile.get_gender_display()
                ),
                "tests": tests,
                "packages": packages,
            }
        )
    return {
        "address": str(address or "").strip(),
        "primary_patient_name": primary["name"],
        "primary_patient_number": primary["phone"],
        "slot_datetime": slot_datetime,
        "payment_type": "paid_by_group",
        "partner_notes": notes or "",
        "patient_details": patient_details,
    }


def transform_serviceability_response(response_payload, status_code):
    status_text = ""
    if isinstance(response_payload, dict):
        status_text = str(response_payload.get("status") or "")

    request_date_servicible_status = True
    address_servicible_status = True
    time_slots = {
        "morning_slot": [],
        "afternoon_slot": [],
        "evening_slot": [],
    }

    if status_code == 400 and status_text == "Past or invalid date":
        request_date_servicible_status = False
    elif status_code == 400 and status_text == "Unable to geocode address":
        address_servicible_status = False
    elif status_code == 400:
        request_date_servicible_status = False
        address_servicible_status = False

    if isinstance(response_payload, dict):
        if status_text == "Location is serviceable":
            address_servicible_status = True
        slots = response_payload.get("slots") or response_payload.get("time_slots") or {}
        if not slots:
            request_date_servicible_status = False
        else:
            time_slots = _bucket_serviceability_slots(slots)
            if not any(time_slots.values()):
                request_date_servicible_status = False

    return {
        "request_date_servicible_status": request_date_servicible_status,
        "address_servicible_status": address_servicible_status,
        "time_slots": time_slots,
    }


def _bucket_serviceability_slots(slots):
    if isinstance(slots, dict) and (
        "morning_slot" in slots
        or "morning" in slots
        or "afternoon_slot" in slots
        or "afternoon" in slots
        or "evening_slot" in slots
        or "evening" in slots
    ):
        return {
            "morning_slot": _normalize_slot_list(
                slots.get("morning_slot") or slots.get("morning") or []
            ),
            "afternoon_slot": _normalize_slot_list(
                slots.get("afternoon_slot") or slots.get("afternoon") or []
            ),
            "evening_slot": _normalize_slot_list(
                slots.get("evening_slot") or slots.get("evening") or []
            ),
        }

    morning_slot = []
    afternoon_slot = []
    evening_slot = []
    slot_items = slots.values() if isinstance(slots, dict) else slots
    for slot in slot_items:
        if not isinstance(slot, dict):
            continue
        datetime_value = slot.get("datetime") or slot.get("slot_datetime")
        if not datetime_value:
            continue
        entry = {"datetime": datetime_value}
        if slot.get("is_morning_slot"):
            morning_slot.append(entry)
        elif slot.get("is_afternoon_slot"):
            afternoon_slot.append(entry)
        elif slot.get("is_evening_slot"):
            evening_slot.append(entry)
    return {
        "morning_slot": morning_slot,
        "afternoon_slot": afternoon_slot,
        "evening_slot": evening_slot,
    }


def _normalize_slot_list(slots):
    normalized = []
    for slot in slots:
        if isinstance(slot, dict):
            datetime_value = slot.get("datetime") or slot.get("slot_datetime")
            if datetime_value:
                normalized.append({"datetime": datetime_value})
        elif slot:
            normalized.append({"datetime": slot})
    return normalized


def sum_decimal(values):
    total = Decimal("0.00")
    for value in values:
        total += Decimal(str(value))
    return total
