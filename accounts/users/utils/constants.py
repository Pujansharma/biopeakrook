from django.utils.translation import gettext_lazy as _

PHONE_NUMBER_MAX_LENGTH = 15


class Gender:
    MALE = "0"
    FEMALE = "1"
    OTHER = "2"

    CHOICES = (
        (MALE, _("Male")),
        (FEMALE, _("Female")),
        (OTHER, _("Other")),
    )

    MAPPING = {
        MALE: "Male",
        FEMALE: "Female",
        OTHER: "Other",
    }
