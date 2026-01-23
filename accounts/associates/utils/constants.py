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


class SpecializationRole:
    OTHER = 'other'
    CENTER_ADMIN = 'center_admin'
    DOCTOR = "doctor"
    HEALTH_COACH = "health_coach"
    CARE_COORDINATOR = "care_coordinator"
    RADIOLOGY_TECH = "radiology_tech"
    PHLEBOTOMIST = "phlebotomist"
    CHIVASOM = "chivasom"
    EXERCISE_PHYSIOLOGIST = "exercise_physiologist"
    PHYSIOTHERAPIST = "physiotherapist"

    CHOICES = (
        (OTHER, 'Other'),
        (CENTER_ADMIN, "Center Admin"),
        (DOCTOR, "Doctor"),
        (HEALTH_COACH, "Health Coach"),
        (CARE_COORDINATOR, "Care Coordinator"),
        (RADIOLOGY_TECH, "Radiology Technician"),
        (PHLEBOTOMIST, "Phlebotomist"),
        (CHIVASOM, "Chivasom"),
        (EXERCISE_PHYSIOLOGIST, "Exercise Physiologist"),
        (PHYSIOTHERAPIST, "Physiotherapist"),
    )
