from django.utils.translation import gettext_lazy as _

PHONE_NUMBER_MAX_LENGTH = 15


class Gender:
    MALE = "0"
    FEMALE = "1"

    CHOICES = (
        (MALE, _("Male")),
        (FEMALE, _("Female")),
    )
