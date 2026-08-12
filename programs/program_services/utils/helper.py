import hashlib

from django.core.files.uploadedfile import UploadedFile


def generate_uploaded_file_hash(uploaded_file: UploadedFile):
    file_hasher = hashlib.sha256()
    for file_chunk in uploaded_file.chunks():
        file_hasher.update(file_chunk)
    uploaded_file.seek(0)
    return file_hasher.hexdigest()
