from sequences.utils import get_next_sequence


def get_composite_template_uid():
    name = "P"
    value = get_next_sequence(name, fill_length=4)
    return value
