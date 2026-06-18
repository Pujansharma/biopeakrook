from django.contrib.postgres.fields import ArrayField
from django.db import models

from accounts.utils import get_user_model
from core.utils.fields import PhoneNumberField
from core.utils.models import BaseUUIDModel, BaseModel
from products.utils.constants import ProviderCallbackFunction, ProductCallbackFunction

User = get_user_model()


class Provider(BaseUUIDModel):
    name = models.CharField(max_length=200)
    callback = models.CharField(choices=ProviderCallbackFunction)
    code = models.CharField(db_index=True, editable=False)
    image = models.ImageField(upload_to="providers/", null=True, blank=True)
    website = models.URLField(null=True, blank=True)
    contact_first_name = models.CharField(null=True, blank=True)
    contact_last_name = models.CharField(null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = PhoneNumberField(null=True, blank=True)
    required_fields = ArrayField(
        base_field=models.CharField(max_length=50), null=True, blank=True
    )
    fetch_fields = ArrayField(
        base_field=models.CharField(max_length=50), null=True, blank=True
    )
    is_api_enabled = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_providers",
    )
    products_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ProviderAPI(BaseModel):
    provider = models.OneToOneField(
        Provider, primary_key=True, on_delete=models.CASCADE, related_name="api"
    )
    data = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_provider_apis",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class Product(BaseUUIDModel):
    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, related_name="products"
    )
    image = models.ImageField(upload_to="providers/products/", null=True, blank=True)
    name = models.CharField(max_length=100)
    code = models.CharField(db_index=True, editable=False)
    callback = models.CharField(choices=ProductCallbackFunction)
    data = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_products",
    )
    tags = models.JSONField(null=True, blank=True)
    sample_file = models.FileField(upload_to="products/sample/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
