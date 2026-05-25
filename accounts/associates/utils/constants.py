from django.db import models


class SpecializationType:
    ENDOCRINOLOGY = "endocrinology"
    METABOLIC_HEALTH_OPERATIONS = "metabolic_health_operations"
    DEXA = "dexa"
    ULTRASONOGRAPHY = "usg"
    BLOOD_COLLECTION = "blood_collection"

    CHOICES = (
        (ENDOCRINOLOGY, "Endocrinology"),
        (METABOLIC_HEALTH_OPERATIONS, "Metabolic Health Operations"),
        (DEXA, "DEXA"),
        (ULTRASONOGRAPHY, "Ultrasonography"),
        (BLOOD_COLLECTION, "Blood Collection"),
    )


class AssociateRoleFeature:
    ALL = "all"
    CUSTOMER_ONBOARDING = "customer_onboarding"
    ASSOCIATE_ONBOARDING = "associate_onboarding"
    APPOINTMENTS = "appointments"
    APPOINTMENT_DATA_SCOPE = "appointment_data_scope"
    PACKAGES = "packages"

    CHOICES = (
        (ALL, "All"),
        (CUSTOMER_ONBOARDING, "Customer Onboarding"),
        (ASSOCIATE_ONBOARDING, "Associate Onboarding"),
        (APPOINTMENTS, "Appointments"),
        (APPOINTMENT_DATA_SCOPE, "Appointment Data Scope"),
        (PACKAGES, "Packages"),
    )


class AssociateRoleAbility:
    MANAGE = "manage"
    READ = "read"
    NONE = "none"

    CHOICES = (
        (MANAGE, "Manage"),
        (READ, "Read"),
        (NONE, "None"),
    )


class AssociateRoleTag(models.TextChoices):
    CLINICAL = "clinical", "Clinical"
    NON_CLINICAL = "non_clinical", "Non Clinical"


class AssociateTitle(models.TextChoices):
    DOCTOR = "doctor", "Dr."
    PROFESSOR = "prof", "Prof."
