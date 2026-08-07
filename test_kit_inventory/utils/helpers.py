import re
from datetime import date
from uuid import UUID

from sequences.utils import get_next_sequence

IGNORED_PRODUCT_CODE_WORDS = {"and", "for", "of", "the", "with"}


def normalize_inventory_text(value: str) -> str:
    normalized_value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(normalized_value.split())


def extract_provider_prefix(provider_name: str) -> str:
    alphabetic_characters = "".join(re.findall(r"[A-Za-z]", provider_name)).upper()
    if len(alphabetic_characters) >= 3:
        return alphabetic_characters[:3]
    return alphabetic_characters.ljust(3, "X")


def get_significant_product_words(product_name: str) -> list[str]:
    normalized_name = normalize_inventory_text(product_name)
    all_words = normalized_name.split()
    significant_words = [
        word for word in all_words if word and word not in IGNORED_PRODUCT_CODE_WORDS
    ]
    return significant_words or all_words


def build_fallback_product_code(product_name: str) -> str:
    significant_words = get_significant_product_words(product_name)
    if len(significant_words) >= 3:
        letter_count = min(4, len(significant_words))
        return "".join(word[0] for word in significant_words[:letter_count]).upper()
    joined_value = "".join(significant_words).upper()
    return joined_value[:3].ljust(3, "X")


def get_test_kit_inventory_code(product_name: str) -> str:
    return build_fallback_product_code(product_name)


def get_test_kit_inventory_sequence_name(provider_id: UUID, received_on: date) -> str:
    received_on_suffix = received_on.strftime("%y%m%d")
    provider_suffix = str(provider_id).replace("-", "")[:8]
    return f"tkinv_{provider_suffix}_{received_on_suffix}"


def generate_test_kit_inventory_batch_id(
    provider_id: UUID,
    provider_name: str,
    received_on: date,
) -> str:
    provider_prefix = extract_provider_prefix(provider_name)
    date_suffix = received_on.strftime("%y%m%d")
    sequence_name = get_test_kit_inventory_sequence_name(provider_id, received_on)
    sequence_value = get_next_sequence(sequence_name, fill_length=3)
    return f"{provider_prefix}-{date_suffix}-{sequence_value}"
