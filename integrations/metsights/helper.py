from .sdk import create_metsights_profile, get_metsights_profile


def get_or_create_metsights_profile(
        phone, email, first_name, last_name, gender, age=None, date_of_birth=None
) -> str | None:
    profile_id = get_metsights_profile(phone)
    if profile_id:
        return profile_id

    profile_response = create_metsights_profile(
        phone=phone,
        email=email,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        age=age,
        date_of_birth=date_of_birth
    )
    if not profile_response:
        return None

    profile_data = profile_response.get("data", {}) or {}
    profile_id =  profile_data.get("id")
    return profile_id
