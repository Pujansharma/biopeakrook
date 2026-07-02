from django.db.models.signals import pre_delete
from django.dispatch import receiver

from pre_consultation.models import PreConsultationMedicalReport


@receiver(pre_delete, sender=PreConsultationMedicalReport)
def delete_medical_report_storage(
    sender,
    instance: PreConsultationMedicalReport,
    **kwargs,
) -> None:
    if instance.file:
        instance.file.delete(save=False)
