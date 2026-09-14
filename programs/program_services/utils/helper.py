import hashlib

from django.core.files import File


def generate_file_hash(uploaded_file: File | bytes):
    file_hasher = hashlib.sha256()

    if isinstance(uploaded_file, bytes):
        file_hasher.update(uploaded_file)
        return file_hasher.hexdigest()

    for file_chunk in uploaded_file.chunks():
        file_hasher.update(file_chunk)
    uploaded_file.seek(0)
    return file_hasher.hexdigest()
