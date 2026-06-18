from sequences.utils import get_next_sequence


def generate_provider_code():
    name = "PV"
    sequence = get_next_sequence(name=f"providers", fill_length=4)
    return f"{name}-{sequence}"


def generate_product_code():
    name = "PC"
    sequence = get_next_sequence(name=f"products", fill_length=4)
    return f"{name}-{sequence}"
