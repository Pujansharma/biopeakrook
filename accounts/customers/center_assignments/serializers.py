from django.db import transaction
from rest_framework import serializers

from accounts.centers.serializers import BaseCenterSerializer
from accounts.customers.models import CustomerCenterAssignment
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer


class CustomerCenterAssignmentDetailSerializer(
    BaseModelSerializer
):
    is_primary = serializers.BooleanField(required=True)
    center = BaseCenterSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = CustomerCenterAssignment
        fields = ["id", "center", "is_primary", "created_at", "created_by"]
        read_only_fields = ["id", "center", "created_at", "created_by"]

    def update(
            self,
            instance: CustomerCenterAssignment,
            validated_data: dict,
    ) -> CustomerCenterAssignment:
        is_primary = validated_data.get('is_primary', False)
        if not is_primary and instance.is_primary:
            raise serializers.ValidationError(
                "Primary center cannot be unassigned without setting another center as home center"
            )

        with transaction.atomic():
            if is_primary:
                (
                    CustomerCenterAssignment.objects.filter(
                        customer_profile=instance.customer_profile,
                        is_primary=True,
                    )
                    .exclude(pk=instance.pk)
                    .update(is_primary=False)
                )

            return super().update(instance, validated_data)
