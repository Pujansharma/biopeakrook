from django.utils import timezone
from datetime import date as date_type, datetime
from typing import Union, Optional


def calculate_age(birth_date: Union[date_type, datetime, str, None]) -> Optional[int]:
    """
    Calculate age in years from a birthdate.

    This function calculates a person's age more accurately than simple division
    by 365 days by accounting for leap years and the actual calendar dates.

    Args:
        birth_date: The birthdate. Can be:
            - datetime.date object
            - datetime.datetime object (time component ignored)
            - str in format 'YYYY-MM-DD'
            - None (returns None)

    Returns:
        int: Age in complete years, or None if birth_date is None or invalid

    Raises:
        ValueError: If string date format is invalid
        TypeError: If birth_date is not a supported type

    Examples:
        >>> from datetime import date
        >>> calculate_age(date(2000, 1, 1))  # Assuming today is 2024-01-01
        24
        >>> calculate_age('2000-06-15')
        23  # or 24 depending on current date
        >>> calculate_age(None)
        None
    """
    if birth_date is None:
        return None

    # Handle string input
    if isinstance(birth_date, str):
        try:
            birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(
                f"Invalid date format '{birth_date}'. Expected 'YYYY-MM-DD'"
            )

    # Handle datetime object (extract date part)
    if isinstance(birth_date, datetime):
        birth_date = birth_date.date()

    today = timezone.localdate()

    # Validate birthdate is not in the future
    if birth_date > today:
        raise ValueError("Birth date cannot be in the future")

    # Calculate age accounting for whether birthday has occurred this year
    age = today.year - birth_date.year

    # Subtract 1 if birthday hasn't occurred yet this year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age
