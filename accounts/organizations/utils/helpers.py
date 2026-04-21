from django.utils.text import slugify


def generate_organization_slug(name: str) -> str:
    return slugify(name)
