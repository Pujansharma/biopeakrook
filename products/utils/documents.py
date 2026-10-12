from programs.services.utils.constants import ServiceDocumentType

from .constants import ProductCallbackFunction, ProviderCallbackFunction

AllowedDocumentTypeMap = dict[str, list[ServiceDocumentType]]


BIOPEAK_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.OLIGOSCAN: [ServiceDocumentType.OLIGOSCAN],
    ProductCallbackFunction.BLOOD: [ServiceDocumentType.BLOOD],
    ProductCallbackFunction.SOMFIT: [ServiceDocumentType.SOMFIT],
    ProductCallbackFunction.COGNIFIT: [
        ServiceDocumentType.BREATHING_STRESS_COGNIFIT,
    ],
    ProductCallbackFunction.STRESS: [
        ServiceDocumentType.BREATHING_STRESS_PROFILE_REPORT,
    ],
    ProductCallbackFunction.PHYSICAL_FUNCTION: [
        ServiceDocumentType.FITNESS_STRENGTH_PHYSICAL_ASSESSMENT,
    ],
    ProductCallbackFunction.PELVIC_FLOOR: [
        ServiceDocumentType.FITNESS_STRENGTH_PELVIC_FLOOR,
    ],
    ProductCallbackFunction.ULTRASOUND_ABDOMEN_PELVIS: [
        ServiceDocumentType.USG_ABDOMEN_PELVIS,
        ServiceDocumentType.USG_ARTERIAL_DOPPLER,
        ServiceDocumentType.USG_VENOUS_DOPPLER,
        ServiceDocumentType.USG_SCROTUM,
        ServiceDocumentType.USG_FOLLICULAR_TVS,
        ServiceDocumentType.USG_PELVIC_TVS,
        ServiceDocumentType.USG_OTHERS,
    ],
    ProductCallbackFunction.ULTRASOUND_CAROTID_DOPPLER: [
        ServiceDocumentType.USG_CAROTID_DOPPLER,
    ],
    ProductCallbackFunction.ULTRASOUND_BREAST: [
        ServiceDocumentType.USG_SONOMAMMOGRAM,
    ],
    ProductCallbackFunction.ULTRASOUND_NECK_THYROID: [
        ServiceDocumentType.USG_NECK,
    ],
    ProductCallbackFunction.PSYCHOPHYSIOLOGICAL: [
        ServiceDocumentType.BREATHING_STRESS_PROFILE_REPORT,
        ServiceDocumentType.BREATHING_STRESS_RESPIRATORY_REPORT,
        ServiceDocumentType.BREATHING_STRESS_COMMUNICATION_STYLE,
        ServiceDocumentType.BREATHING_STRESS_COGNIFIT,
    ],
    ProductCallbackFunction.RESPIRATORY_FUNCTION: [
        ServiceDocumentType.BREATHING_STRESS_RESPIRATORY_REPORT,
    ],
    ProductCallbackFunction.DXA_SEGMENTAL_ANALYSIS: [
        ServiceDocumentType.DXA_SEGMENTAL_ANALYSIS,
    ],
    ProductCallbackFunction.DXA_BC_BMD: [
        ServiceDocumentType.DXA_BODY_COMPOSITION,
    ],
    ProductCallbackFunction.DXA_CORE_SCAN: [
        ServiceDocumentType.DXA_CORE_SCAN,
    ],
    ProductCallbackFunction.VO2_MAX: [
        ServiceDocumentType.FITNESS_STRENGTH_VO2_MAX,
    ],
}

METFLUX_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.METSIGHTS_PP: [ServiceDocumentType.METSIGHTS_PP],
}

HEALTHIANS_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.BLOOD: [ServiceDocumentType.BLOOD],
}

ORANGE_LABS_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.BLOOD: [ServiceDocumentType.BLOOD],
}

BUGSPEAKS_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.GUT_MICROBIOME: [
        ServiceDocumentType.BUGSPEAKS_REPORT,
    ],
}

FIVE_C_NETWORK_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.EVO_360: [ServiceDocumentType.EVO_360],
}

STRAND_SHARED_DOCUMENTS = [
    ServiceDocumentType.GENETICS_FUNCTIONAL,
    ServiceDocumentType.GENETICS_BREAST_OVARIAN_CANCER,
    ServiceDocumentType.GENETICS_COMPREHENSIVE,
    ServiceDocumentType.GENETICS_PHARMACOGENOMICS,
    ServiceDocumentType.GENETICS_INHERITED_CANCER,
]

STRAND_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.GENOMICS_WES: STRAND_SHARED_DOCUMENTS,
    ProductCallbackFunction.GENOMICS_HLA_TYPING: STRAND_SHARED_DOCUMENTS,
    ProductCallbackFunction.GENOMICS_SINGLE_GENE_NGS: STRAND_SHARED_DOCUMENTS,
    ProductCallbackFunction.GENOMICS_CANCER_SPOT: STRAND_SHARED_DOCUMENTS,
    ProductCallbackFunction.GENOMICS_HEALTH_INSIGHTS: [
        ServiceDocumentType.GENETICS_HEALTH_INSIGHTS,
    ],
    ProductCallbackFunction.GENOMICS_NUTRI_DNA: [
        ServiceDocumentType.GENETICS_NUTRI_DNA,
    ],
}

META_OMICS_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.OMICS_NUTRI_TOXIC: [
        ServiceDocumentType.STEROID_HORMONE_NUTRITIONAL_TOXIC_ELEMENTS,
    ],
    ProductCallbackFunction.OMICS_NAD_META: [
        ServiceDocumentType.STEROID_HORMONE_NAD_LONGEVITY,
    ],
    ProductCallbackFunction.OMICS_FATTY_ACID: [
        ServiceDocumentType.STEROID_HORMONE_FATTY_ACID_PROFILE,
    ],
    ProductCallbackFunction.OMICS_NEURO: [
        ServiceDocumentType.STEROID_HORMONE_NEUROTRANSMITTER_PROFILE,
    ],
    ProductCallbackFunction.OMICS_STEROID: [
        ServiceDocumentType.STEROID_HORMONE_PROFILE,
    ],
    ProductCallbackFunction.OMICS_URINE: [ServiceDocumentType.OMICS_URINE],
    ProductCallbackFunction.OMICS_SALIVARY_CORTISOL: [
        ServiceDocumentType.OMICS_CORTISOL,
    ],
}

NEUBERG_ANAND_ALLOWED_DOCUMENTS: AllowedDocumentTypeMap = {
    ProductCallbackFunction.BLOOD: [ServiceDocumentType.BLOOD],
}

PRODUCT_DOCUMENTS_MAP: dict[str, AllowedDocumentTypeMap] = {
    ProviderCallbackFunction.BIOPEAK: BIOPEAK_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.METFLUX: METFLUX_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.HEALTHIANS: HEALTHIANS_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.ORANGE_LABS: ORANGE_LABS_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.BUGSPEAKS: BUGSPEAKS_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.FIVE_C_NETWORK: FIVE_C_NETWORK_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.STRAND_LIFE_SCIENCES: STRAND_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.NEUBERG_ANAND: NEUBERG_ANAND_ALLOWED_DOCUMENTS,
    ProviderCallbackFunction.META_OMICS_LABS: META_OMICS_ALLOWED_DOCUMENTS,
}


def _serialize_document_type(document_type: ServiceDocumentType):
    return {
        "display_name": document_type.label,
        "value": document_type.value,
    }


def get_allowed_document_type_choices(provider_code: str, product_code: str):
    if provider_code == ProviderCallbackFunction.OTHER:
        return [*ServiceDocumentType]

    provider_documents = PRODUCT_DOCUMENTS_MAP.get(provider_code, {})
    document_types = provider_documents.get(product_code, [])
    return [*document_types]


def get_allowed_document_types(provider_code: str, product_code: str):
    document_types = get_allowed_document_type_choices(provider_code, product_code)
    return list(map(_serialize_document_type, document_types))


def get_available_document_types(assigned_document_types: set[str]):
    return [
        {
            **_serialize_document_type(document_type),
            "exists": document_type.value in assigned_document_types,
        }
        for document_type in ServiceDocumentType
    ]
