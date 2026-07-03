"""Delete uploaded medical-report files from storage when the DB row is removed."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from pre_consultation.models import PreConsultationMedicalReport


@receiver(post_delete, sender=PreConsultationMedicalReport)
def delete_medical_report_storage(
    sender,
    instance: PreConsultationMedicalReport,
    **kwargs,
) -> None:
    if instance.file:
        transaction.on_commit(lambda file=instance.file: file.delete(save=False))
