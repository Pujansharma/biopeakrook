"""Map CustomerProfile gender values to/from patient_baseline layer gender."""

from accounts.users.utils.constants import Gender
from pre_consultation.utils.constants import PatientBaselineGender

PROFILE_GENDER_TO_BASELINE_GENDER = {
    Gender.MALE: PatientBaselineGender.MALE,
    Gender.FEMALE: PatientBaselineGender.FEMALE,
    Gender.OTHER: PatientBaselineGender.OTHER,
}

BASELINE_GENDER_TO_PROFILE_GENDER = {
    PatientBaselineGender.MALE: Gender.MALE,
    PatientBaselineGender.FEMALE: Gender.FEMALE,
    PatientBaselineGender.OTHER: Gender.OTHER,
}


def profile_gender_to_baseline_gender(profile_gender: str | None) -> str | None:
    if profile_gender is None:
        return None
    return PROFILE_GENDER_TO_BASELINE_GENDER.get(profile_gender)


def baseline_gender_to_profile_gender(baseline_gender: str | None) -> str | None:
    if baseline_gender is None:
        return None
    return BASELINE_GENDER_TO_PROFILE_GENDER.get(baseline_gender)


def baseline_gender_supports_sex_gated_content(gender: str | None) -> bool:
    return gender in (
        PatientBaselineGender.MALE,
        PatientBaselineGender.FEMALE,
    )
