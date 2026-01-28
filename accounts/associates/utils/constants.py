class SpecializationType:
    ENDOCRINOLOGY = 'endocrinology'
    METABOLIC_HEALTH_OPERATIONS = "metabolic_health_operations"
    DEXA = "dexa"
    ULTRASONOGRAPHY = "usg"
    BLOOD_COLLECTION = "blood_collection"

    CHOICES = (
        (ENDOCRINOLOGY, 'Endocrinology'),
        (METABOLIC_HEALTH_OPERATIONS, "Metabolic Health Operations"),
        (DEXA, "DEXA"),
        (ULTRASONOGRAPHY, "Ultrasonography"),
        (BLOOD_COLLECTION, "Blood Collection"),
    )
