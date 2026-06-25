import requests
from django.core.files.base import ContentFile


def fetch_file_from_url(url: str | None) -> ContentFile | None:
    if not url:
        return None
    response = requests.get(url, stream=True)
    if not response.ok:
        return None
    content = response.content
    file = ContentFile(content, name=response.headers.get("name", "Unknown"))
    return file
