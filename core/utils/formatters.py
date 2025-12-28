from typing import Optional

import phonenumbers
from phonenumbers import PhoneNumber
from rest_framework.exceptions import ValidationError


class PhoneNumberFormat:
    def __init__(self, value, region="IN"):
        self.value = str(value)
        self.region = region
        self._parsed_number = None
        self._is_parsed = False

    def _parse_phone_number(self) -> Optional[PhoneNumber]:
        """Internal method to parse phone number string into PhoneNumber object."""
        try:
            parsed = phonenumbers.parse(self.value, region=self.region)
            return parsed
        except phonenumbers.NumberParseException:
            return None

    def _get_formatted_number(self):
        """
        Internal method to parse and format phone number.

        Returns:
            tuple: (formatted_string, is_valid, parsed_number) where:
                - formatted_string: +CountryCode-NationalNumber format or None
                - is_valid: boolean indicating if number is valid
                - parsed_number: PhoneNumber object or None
        """
        parsed = self._parse_phone_number()

        if parsed is None:
            return None, False, None

        is_possible = phonenumbers.is_possible_number(parsed)
        is_valid = phonenumbers.is_valid_number(parsed)

        if is_possible and is_valid:
            formatted = f"+{parsed.country_code}-{parsed.national_number}"
            return formatted, True, parsed

        return None, False, parsed

    def clean(self, raise_exception=False) -> Optional[str]:
        """
        Returns the cleaned phone number string or raises ValidationError if invalid.

        Args:
            raise_exception (bool): If True, raises ValidationError for invalid numbers.
                                  If False, returns None for invalid numbers.

        Returns:
            str: Cleaned phone number in +CountryCode-NationalNumber format
            None: If raise_exception=False and number is invalid

        Raises:
            ValidationError: If raise_exception=True and number is invalid
        """
        formatted, is_valid, _ = self._get_formatted_number()

        if is_valid:
            return formatted

        if raise_exception:
            raise ValidationError("The number supplied does not seem to be a valid phone number.")

        return None

    @property
    def phonenumber(self) -> Optional[PhoneNumber]:
        """Returns the parsed PhoneNumber object or None if parsing fails."""
        if not self._is_parsed:
            self._parsed_number = self._parse_phone_number()
            self._is_parsed = True
        return self._parsed_number

    def is_valid(self) -> bool:
        """Check if the phone number is valid."""
        phone_obj = self.phonenumber
        return phone_obj is not None and phonenumbers.is_valid_number(phone_obj)

    def is_possible(self) -> bool:
        """Check if the phone number is possible."""
        phone_obj = self.phonenumber
        return phone_obj is not None and phonenumbers.is_possible_number(phone_obj)

    def get_country_code(self) -> Optional[int]:
        """Get the country code of the phone number."""
        phone_obj = self.phonenumber
        if not phone_obj:
            return None
        return phone_obj.country_code

    def get_national_number(self) -> Optional[int]:
        """Get the national number portion of the phone number."""
        phone_obj = self.phonenumber
        if not phone_obj:
            return None
        return phone_obj.national_number
