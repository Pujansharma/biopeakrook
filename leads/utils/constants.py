from django.db import models


class LeadPackages(models.TextChoices):
    ESSENTIAL_HEALTH = "P001", "Essential Health Program"
    ESSENTIAL_HEALTH_DIGITAL_TWIN = "P002", "Essential Health with Digital Twin"
    EDGE = "P003", "Edge Program"
    EDGE_PLUS = "P004", "Edge Plus Program"
    ELITE_LONGEVITY = "P005", "Elite Longevity Programme"
    CUSTOMISED = "P006", "Customised Program"


LEAD_V1_CREATE_DEPRECATED = "POST /leads/ is deprecated. Use POST /leads/v2/."
LEAD_V1_LIST_DEPRECATED = "GET /leads/ is deprecated. Use GET /leads/v2/."
LEAD_V1_GET_DEPRECATED = "GET /leads/{id}/ is deprecated. Use GET /leads/v2/{id}/."
LEAD_V1_UPDATE_DEPRECATED = "PATCH /leads/{id}/ is deprecated. Use PATCH /leads/v2/{id}/."
