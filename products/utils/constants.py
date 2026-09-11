from functools import partial

from django.db import models


class ProviderCallbackFunction(models.TextChoices):
    OTHER = "other", "Other"
    BIOPEAK = "biopeak", "Biopeak"
    METFLUX = "metflux", "MetFlux"
    HEALTHIANS = "healthians", "Healthians"
    ORANGE_LABS = "orange_labs", "Orange Labs"
    BUGSPEAKS = "bugspeaks", "BugSpeaks"
    FIVE_C_NETWORK = "5c_network", "5C Network"
    STRAND_LIFE_SCIENCES = "strand_life_sciences", "Strand Life Sciences"
    NEUBERG_ANAND = "neuberg_anand", "Neuberg Anand"
    META_OMICS_LABS = "meta_omics_labs", "Meta Omics Labs"
    YAAZH_XENOMICS = "yaazh_xenomics", "Yaazh Xenomics"


class ProductCallbackFunction(models.TextChoices):
    OTHER = "other", "Other"
    BLOOD = "blood", "Blood Diagnostics"
    DXA = "dxa", "DXA Scan"
    DXA_SEGMENTAL_ANALYSIS = "dxa_segmental_analysis", "DXA – Segmental Analysis"
    DXA_BC_BMD = "dxa_bc_bmd", "DXA – Body Composition & BMD"
    DXA_CORE_SCAN = "dxa_core", "DXA – Core Scan"
    EVO_360 = "evo_360", "EVO 360"
    GUT_MICROBIOME = "gut_microbiome", "Gut Microbiome"
    METSIGHTS_PP = "metsights_precision_mhap", "MetSights Precision Plus – Analysis & Protocol"
    VO2_MAX = "vo2_max", "Exercise Physiology – VO2 Max"
    OMICS_NUTRI_TOXIC = "omics_nutri_toxic", "Omics – Nutritional & Toxic Elements"
    OMICS_NAD_META = "omics_nad_meta", "Omics – NAD Metabolism"
    OMICS_FATTY_ACID = "omics_fatty_acid", "Omics – Fatty Acid Profile"
    OMICS_NEURO = "omics_neuro", "Omics – Neurotransmitter Profile"
    OMICS_STEROID = "omics_steroid", "Omics – Steroid Hormone Profile"
    OMICS_URINE = "omics_urine", "Omics – Urine Metabolites"
    OMICS_SALIVARY_CORTISOL = "omics_salivary_cortisol", "Omics – Salivary Cortisol"
    OLIGOSCAN = "oligoscan", "OligoScan Screening"
    SOMFIT = "somfit", "Sleep Monitoring – SOMFIT"
    COGNIFIT = "cognifit", "Cognitive Testing – CogniFit"
    STRESS = "stress", "Stress Profile"
    PHYSICAL_FUNCTION = "physical_function", "Physical Function"
    PELVIC_FLOOR = "pelvic_floor", "Pelvic Floor Function"
    ULTRASOUND_ABDOMEN_PELVIS = "ultrasound_abdomen_pelvis", "Ultrasound – Abdomen & Pelvis"
    ULTRASOUND_CAROTID_DOPPLER = "ultrasound_carotid_doppler", "Ultrasound – Carotid Doppler"
    ULTRASOUND_BREAST = "ultrasound_breast", "Ultrasound – Breast"
    ULTRASOUND_NECK_THYROID = "ultrasound_neck_thyroid", "Ultrasound – Neck & Thyroid"
    PSYCHOPHYSIOLOGICAL = "psychophysiological", "Psychophysiological Profile"
    RESPIRATORY_FUNCTION = "respiratory_function", "Respiratory Function"
    GENOMICS_WES = "genomics_wes", "Genomics WES"
    GENOMICS_HLA_TYPING = "genomics_hla_typing", "Genomics HLA Typing"
    GENOMICS_SINGLE_GENE_NGS = "genomics_single_gene_ngs", "Genomics Single Gene NGS"
    GENOMICS_CANCER_SPOT = "genomics_cancerspot", "Genomics CancerSpot"
    GENOMICS_HEALTH_INSIGHTS = "genomics_health_insights", "Genomics Health Insights"
    GENOMICS_NUTRI_DNA = "genomics_nutri_dna", "Genomics NutriDNA"


PROVIDER_PRODUCT_CALLBACK_MAP: dict[str, list[ProductCallbackFunction]] = {
    ProviderCallbackFunction.OTHER: [
        ProductCallbackFunction.OTHER,
    ],
    ProviderCallbackFunction.BIOPEAK: [
        ProductCallbackFunction.OLIGOSCAN,
        ProductCallbackFunction.BLOOD,
        ProductCallbackFunction.SOMFIT,
        ProductCallbackFunction.COGNIFIT,
        ProductCallbackFunction.STRESS,
        ProductCallbackFunction.PHYSICAL_FUNCTION,
        ProductCallbackFunction.PELVIC_FLOOR,
        ProductCallbackFunction.ULTRASOUND_ABDOMEN_PELVIS,
        ProductCallbackFunction.ULTRASOUND_CAROTID_DOPPLER,
        ProductCallbackFunction.ULTRASOUND_BREAST,
        ProductCallbackFunction.ULTRASOUND_NECK_THYROID,
        ProductCallbackFunction.PSYCHOPHYSIOLOGICAL,
        ProductCallbackFunction.RESPIRATORY_FUNCTION,
        ProductCallbackFunction.DXA_SEGMENTAL_ANALYSIS,
        ProductCallbackFunction.DXA_BC_BMD,
        ProductCallbackFunction.DXA_CORE_SCAN,
        ProductCallbackFunction.VO2_MAX,
    ],
    ProviderCallbackFunction.HEALTHIANS: [
        ProductCallbackFunction.BLOOD,
    ],
    ProviderCallbackFunction.METFLUX: [
        ProductCallbackFunction.METSIGHTS_PP,
    ],
    ProviderCallbackFunction.ORANGE_LABS: [
        ProductCallbackFunction.BLOOD
    ],
    ProviderCallbackFunction.BUGSPEAKS: [
        ProductCallbackFunction.GUT_MICROBIOME,
    ],
    ProviderCallbackFunction.FIVE_C_NETWORK: [
        ProductCallbackFunction.EVO_360
    ],
    ProviderCallbackFunction.STRAND_LIFE_SCIENCES: [
        ProductCallbackFunction.GENOMICS_WES,
        ProductCallbackFunction.GENOMICS_HLA_TYPING,
        ProductCallbackFunction.GENOMICS_SINGLE_GENE_NGS,
        ProductCallbackFunction.GENOMICS_CANCER_SPOT,
        ProductCallbackFunction.GENOMICS_HEALTH_INSIGHTS,
        ProductCallbackFunction.GENOMICS_NUTRI_DNA,
    ],
    ProviderCallbackFunction.META_OMICS_LABS: [
        ProductCallbackFunction.OMICS_NUTRI_TOXIC,
        ProductCallbackFunction.OMICS_NAD_META,
        ProductCallbackFunction.OMICS_FATTY_ACID,
        ProductCallbackFunction.OMICS_NEURO,
        ProductCallbackFunction.OMICS_STEROID,
        ProductCallbackFunction.OMICS_URINE,
        ProductCallbackFunction.OMICS_SALIVARY_CORTISOL,
    ],
    ProviderCallbackFunction.NEUBERG_ANAND: [
        ProductCallbackFunction.BLOOD,
    ]
}


class FetchProfileFieldChoices(models.TextChoices):
    FULL_NAME = "full_name", "Full Name"
    AGE = "age", "Age"
    GENDER = "gender", "Gender"
    DATE_OF_BIRTH = "date_of_birth", "Date of Birth"
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"


def _matches_provider(provider_filter: str, item: tuple[str, list]) -> bool:
    return item[0] == provider_filter


def _serialize_callback(callback: ProductCallbackFunction) -> dict:
    return {"value": callback.value, "display_name": callback.label}


def _serialize_provider_entry(
        item: tuple[str, list[ProductCallbackFunction]],
) -> tuple[str, list[dict]]:
    provider, callbacks = item
    return provider, list(map(_serialize_callback, callbacks))


def get_callback_options(provider_filter: str | None) -> list[dict]:
    matches = partial(_matches_provider, provider_filter)
    source = dict(filter(matches, PROVIDER_PRODUCT_CALLBACK_MAP.items()))

    data = dict(map(_serialize_provider_entry, source.items()))
    return next(iter(data.values()), [])
