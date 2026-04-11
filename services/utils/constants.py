from django.db import models


class ServiceCategory(models.TextChoices):
    CONSULTATION = 'consultation', 'Consultation'
    THERAPY = 'therapy', 'Therapy'
    DIAGNOSTIC = 'diagnostic', 'Diagnostic Test'
    WELLNESS = 'wellness', 'Wellness Program'
    SCREENING = 'screening', 'Health Screening'
    PROCEDURE = 'procedure', 'Medical Procedure'
