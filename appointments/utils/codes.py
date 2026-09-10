from accounts.centers.models import Center
from sequences.utils import get_next_sequence


def generate_appointment_code(center):
    sequence_value = get_next_sequence(
        name=f"appointments_{center.pk}",
        fill_length=5,
    )
    return f"APT-{center.code}-{sequence_value}"
