class RoomType:
    CONSULTATION = "consultation"
    THERAPY = "therapy"
    BLOOD_COLLECTION = "blood_collection"
    IMAGING = "imaging"
    LAB = "lab"
    WAITING = "waiting"

    CHOICES = (
        (CONSULTATION, "Consultation Room"),
        (THERAPY, "Therapy Room"),
        (BLOOD_COLLECTION, "Blood Collection Room"),
        (IMAGING, "Imaging Room"),
        (LAB, "Laboratory"),
        (WAITING, "Waiting Area"),
    )


class DeviceType:
    SAMPLING_DEVICE = "sampling_device"
    DEXA_MACHINE = "dexa_machine"
    ULTRASOUND = "ultrasound"
    LAB_ANALYZER = "lab_analyzer"
    THERAPY_EQUIPMENT = "therapy_equipment"

    CHOICES = (
        (SAMPLING_DEVICE, "Blood Sampling Device"),
        (DEXA_MACHINE, "DEXA Machine"),
        (ULTRASOUND, "Ultrasound Machine"),
        (LAB_ANALYZER, "Lab Analyzer"),
        (THERAPY_EQUIPMENT, "Therapy Equipment"),
    )
