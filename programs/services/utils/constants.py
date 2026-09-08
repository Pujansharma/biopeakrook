from django.db import models


class ServiceCategory(models.TextChoices):
    THERAPY = "therapy", "Therapy"
    CONSULTATION = "consultation", "Consultation"
    ASSESSMENT = "assessment", "Assessment"


class ServiceDocumentType(models.TextChoices):
    OTHER = "other", "Other"
    BLOOD = "blood", "Blood diagnostics Report"
    OLIGOSCAN = "oligoscan", "OligoScan Report"
    SOMFIT = "somfit", "SOMFIT Report"
    METSIGHTS_PP = "metsights_pp", "MetSights Precision Plus Report"
    EVO_360 = "evo_360", "EVO 360 Report"
    OMICS_URINE = "omics_urine", "Urine Metabolites Report"
    OMICS_CORTISOL = "omics_cortisol", "Salivary Cortisol Report"

    DXA_CORE_SCAN = "dxa_core_scan", "Core Scan"
    DXA_BODY_COMPOSITION = "dxa_body_composition", "Body Composition"
    DXA_SEGMENTAL_ANALYSIS = "dxa_segmental_analysis", "Segmental Analysis"

    BREATHING_STRESS_PROFILE_REPORT = (
        "breathing_stress_profile_report",
        "Stress Profile Report",
    )

    BREATHING_STRESS_RESPIRATORY_REPORT = (
        "breathing_stress_respiratory_report",
        "Respiratory Report",
    )
    BREATHING_STRESS_COMMUNICATION_STYLE = (
        "breathing_stress_communication_style",
        "Communication Style",
    )
    BREATHING_STRESS_COGNIFIT = "breathing_stress_cognifit", "Cognifit"

    USG_CAROTID_DOPPLER = "usg_carotid_doppler", "Bilateral Carotid Doppler"
    USG_NECK = "usg_neck", "Neck & Thyroid"
    USG_ABDOMEN_PELVIS = "usg_abdomen_pelvis", "Abdomen & Pelvis"
    USG_ARTERIAL_DOPPLER = "usg_arterial_doppler", "Arterial Doppler"
    USG_VENOUS_DOPPLER = "usg_venous_doppler", "Venous Doppler"
    USG_SONOMAMMOGRAM = "usg_sonomammogram", "Sonomammogram"
    USG_SCROTUM = "usg_scrotum", "Scrotum"
    USG_FOLLICULAR_TVS = "usg_follicular_tvs", "Follicular (TVS)"
    USG_PELVIC_TVS = "usg_pelvic_tvs", "Pelvic (TVS)"
    USG_OTHERS = "usg_others", "Others (USG)"

    GENETICS_FUNCTIONAL = "genetics_functional", "Functional Genetics"
    GENETICS_NUTRI_DNA = "genetics_nutri_dna", "NutriDNA"
    GENETICS_HEALTH_INSIGHTS = "genetics_health_insights", "Genomic Health Insights"
    GENETICS_BREAST_OVARIAN_CANCER = (
        "genetics_breast_ovarian_cancer",
        "Breast & Ovarian Cancer",
    )
    GENETICS_COMPREHENSIVE = "genetics_comprehensive", "Comprehensive Genetics"
    GENETICS_PHARMACOGENOMICS = "genetics_pharmacogenomics", "Pharmacogenomics"
    GENETICS_INHERITED_CANCER = "genetics_inherited_cancer", "Inherited Cancer Genetics"
    GENETICS_NUTRI_DNA_PDF = "genetics_nutri_dna_pdf", "NutriDNA PDF"
    GENETICS_NUTRI_DNA_VCF = "genetics_nutri_dna_vcf", "NutriDNA VCF"

    BUGSPEAKS_REPORT = "bugspeaks_report", "Bugspeaks Report"

    # Functional & Metabolic Tests
    STEROID_HORMONE_PROFILE = "steroid_hormone_profile", "Steroid Hormone Profile"
    STEROID_HORMONE_NAD_LONGEVITY = (
        "steroid_hormone_nad_longevity",
        "NAD+ Longevity Metabolism",
    )
    STEROID_HORMONE_NUTRITIONAL_TOXIC_ELEMENTS = (
        "steroid_hormone_nutri_toxic",
        "Nutritional & Toxic Elements",
    )
    STEROID_HORMONE_FATTY_ACID_PROFILE = (
        "steroid_hormone_fatty_acid",
        "Fatty Acid (Omega 3) profile",
    )
    STEROID_HORMONE_NEUROTRANSMITTER_PROFILE = (
        "steroid_hormone_neurotransmitter_profile",
        "Neurotransmitter profile",
    )
    FITNESS_STRENGTH_PELVIC_FLOOR = (
        "fitness_strength_pelvic_floor",
        "Pelvic Floor Assessment",
    )
    FITNESS_STRENGTH_PHYSICAL_ASSESSMENT = (
        "fitness_strength_physical_assessment",
        "Physical Assessment",
    )
    FITNESS_STRENGTH_VO2_MAX = ("fitness_strength_vo2_max", "VO₂ max Report")


class ServiceDocumentCategory(models.TextChoices):
    REPORT = "report", "Report file"
    RAW = "raw", "Raw data file"


class ServiceResultMode(models.TextChoices):
    UPLOAD = "upload", "Upload"
    FETCH = "fetch", "Fetch"


class ResultRequestStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ModuleCategoryType(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    CLINICAL_LAB_DIAGNOSTICS = "clinical_lab_diagnostics", "Clinical Lab Diagnostics"
    FUNCTIONAL_METABOLIC_TESTS = (
        "functional_metabolic_tests",
        "Functional & Metabolic Tests",
    )
    GENETICS = "genetics", "Genetics"
    IMAGING_BODY_ANALYSIS = "imaging_body_analysis", "Imaging & Body Analysis"
    PSYCHOPHYSIOLOGY_AND_PERFORMANCE = (
        "psychophysiology_performance",
        "Psychophysiology & Performance",
    )
    CONSULTATION_NOTES = "consultation_notes", "Consultation Notes"
    RISK_LANDSCAPE_ROOT_CAUSE = (
        "risk_landscape_rootcause",
        "Risk Landscape & Root cause",
    )


SERVICE_DOCUMENT_MODULE_CATEGORY_MAP = {
    ServiceDocumentType.OTHER: ModuleCategoryType.UNKNOWN,
    ServiceDocumentType.BLOOD: ModuleCategoryType.CLINICAL_LAB_DIAGNOSTICS,
    ServiceDocumentType.OLIGOSCAN: ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS,
    ServiceDocumentType.METSIGHTS_PP: ModuleCategoryType.RISK_LANDSCAPE_ROOT_CAUSE,
    ServiceDocumentType.EVO_360: ModuleCategoryType.RISK_LANDSCAPE_ROOT_CAUSE,
    ServiceDocumentType.OMICS_URINE: ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS,
    ServiceDocumentType.OMICS_CORTISOL: ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS,
    ServiceDocumentType.DXA_CORE_SCAN: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.DXA_BODY_COMPOSITION: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.DXA_SEGMENTAL_ANALYSIS: (
        ModuleCategoryType.IMAGING_BODY_ANALYSIS
    ),
    ServiceDocumentType.SOMFIT: ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE,
    ServiceDocumentType.BREATHING_STRESS_PROFILE_REPORT: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.BREATHING_STRESS_RESPIRATORY_REPORT: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.BREATHING_STRESS_COMMUNICATION_STYLE: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.BREATHING_STRESS_COGNIFIT: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.USG_CAROTID_DOPPLER: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_NECK: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_ABDOMEN_PELVIS: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_ARTERIAL_DOPPLER: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_VENOUS_DOPPLER: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_SONOMAMMOGRAM: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_SCROTUM: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_FOLLICULAR_TVS: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_PELVIC_TVS: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.USG_OTHERS: ModuleCategoryType.IMAGING_BODY_ANALYSIS,
    ServiceDocumentType.GENETICS_FUNCTIONAL: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_NUTRI_DNA: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_HEALTH_INSIGHTS: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_BREAST_OVARIAN_CANCER: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_COMPREHENSIVE: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_PHARMACOGENOMICS: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_INHERITED_CANCER: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_NUTRI_DNA_PDF: ModuleCategoryType.GENETICS,
    ServiceDocumentType.GENETICS_NUTRI_DNA_VCF: ModuleCategoryType.GENETICS,
    ServiceDocumentType.BUGSPEAKS_REPORT: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.STEROID_HORMONE_PROFILE: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.STEROID_HORMONE_NAD_LONGEVITY: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.STEROID_HORMONE_NUTRITIONAL_TOXIC_ELEMENTS: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.STEROID_HORMONE_FATTY_ACID_PROFILE: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.STEROID_HORMONE_NEUROTRANSMITTER_PROFILE: (
        ModuleCategoryType.FUNCTIONAL_METABOLIC_TESTS
    ),
    ServiceDocumentType.FITNESS_STRENGTH_PELVIC_FLOOR: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.FITNESS_STRENGTH_PHYSICAL_ASSESSMENT: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
    ServiceDocumentType.FITNESS_STRENGTH_VO2_MAX: (
        ModuleCategoryType.PSYCHOPHYSIOLOGY_AND_PERFORMANCE
    ),
}


def get_service_document_module_category(document_type: str):
    return SERVICE_DOCUMENT_MODULE_CATEGORY_MAP.get(
        document_type,
        ModuleCategoryType.UNKNOWN,
    )


def get_module_category_document_types(module_category: str):
    return [
        document_type.value
        for document_type in ServiceDocumentType
        if get_service_document_module_category(document_type) == module_category
    ]
