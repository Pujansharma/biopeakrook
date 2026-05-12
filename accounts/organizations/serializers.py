from django.utils.text import slugify

from accounts.organizations.models import Organization
from core.utils.serializers import BaseModelSerializer


class OrganizationSerializer(BaseModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "description",
            "image",
            "centers_count",
            "inactive_centers_count",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "code",
            "slug",
            "centers_count",
            "inactive_centers_count",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
        ]

    def update(self, instance, validated_data):
        validated_data.pop("slug", None)
        if "name" in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])
        return super().update(instance, validated_data)
