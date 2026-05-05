from django.db import transaction
from django.db.models import F

from sequences.models import Sequence


@transaction.atomic
def generate_sequence(sequence_name):
    sequence, _ = Sequence.objects.update_or_create(
        name=sequence_name.lower(),
        defaults={
            "last_value": F("last_value") + 1,
        },
        create_defaults={"last_value": 1},
    )
    sequence.refresh_from_db()
    return sequence.last_value


@transaction.atomic
def generate_sequences_bulk(sequence_name, count=1):
    """
    Reserve multiple sequential values efficiently.

    Args:
        sequence_name: Name of the sequence
        count: Number of sequential values to reserve

    Returns:
        range object containing the reserved values

    """
    if count < 1:
        raise ValueError("Count must be at least 1")

    sequence, _ = Sequence.objects.update_or_create(
        name=sequence_name.lower(),
        defaults={"last_value": F("last_value") + count},
        create_defaults={"last_value": count},
    )
    sequence.refresh_from_db()

    # Return range: (last_value - count + 1) to last_value (inclusive)
    start_value = sequence.last_value - count + 1
    return range(start_value, sequence.last_value + 1)


def get_next_sequence(name, fill_length=0):
    last_value = generate_sequence(name)
    return f"{last_value}".zfill(fill_length)


def get_next_sequences_bulk(name, count=1, fill_length=0):
    """
    Get multiple sequential values as zero-padded strings.

    Args:
        name: Name of the sequence
        count: Number of sequential values to get
        fill_length: Zero-padding length

    Returns:
        List of zero-padded string values

    """
    values = generate_sequences_bulk(name, count)
    return [str(val).zfill(fill_length) for val in values]
