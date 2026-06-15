from rest_framework import serializers

from accounts.associates.serializers import (
    BaseAssociateRoleSerializer,
    AssociateSourceMixinSerializer,
)
from accounts.centers.serializers import MinimumCenterSerializer
from accounts.customers.models import CustomerProfile, CustomerAssociateAssignment
from accounts.users.utils.constants import Gender
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer
from programs.models import ProgramService, TherapyProgram
from programs.services.models import Service
from programs.utils.constants import ProgramType


class ExternalCustomerServiceSerializer(BaseModelSerializer):
    centers = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Service
        fields = ["id", "name", "centers"]

    def get_centers(self, instance):
        assignments = instance.center_assignments.select_related("center").filter(
            is_active=True
        )[:10]
        if not assignments:
            return None
        centers = [asg.center for asg in assignments]
        return MinimumCenterSerializer(centers, many=True, context=self.context).data


class ExternalProgramServiceSerializer(BaseModelSerializer):
    service = ExternalCustomerServiceSerializer(read_only=True)
    sessions_count = serializers.IntegerField(
        source="therapy_service.sessions_count", read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="therapy_service.sessions_used", read_only=True
    )
    redeem_code = serializers.CharField(
        source="therapy_service.redeem_code", read_only=True
    )

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "redeem_code",
            "created_at",
            "is_active",
            "cancelled_at",
        ]


class CustomerTherapyProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type", choices=ProgramType, default=ProgramType.THERAPY
    )

    expires_at = serializers.DateField(source="program.expires_at", required=True)
    # is_complimentary = serializers.BooleanField(
    #     source="program.is_complimentary", default=True
    # )
    # price = serializers.DecimalField(
    #     source="program.price",
    #     allow_null=True,
    #     required=False,
    #     max_digits=10,
    #     decimal_places=2,
    # )
    services_count = serializers.IntegerField(
        source="program.services_count", default=0, read_only=True
    )

    # redeemable_centers_count = serializers.IntegerField(
    #     source="program.redeemable_centers_count", default=0, read_only=True
    # )

    class Meta:
        model = TherapyProgram
        fields = [
            "id",
            "program_type",
            "expires_at",
            "services_count",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def create(self, validated_data):
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "program_type":
            rep["program_type"] = instance.program.get_program_type_display()
        return rep


class CustomerTherapyProgramDetailSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type", choices=ProgramType, read_only=True
    )
    is_complimentary = serializers.BooleanField(
        source="program.is_complimentary", read_only=True
    )
    price = serializers.DecimalField(
        source="program.price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )

    expires_at = serializers.DateField(
        source="program.expires_at", required=False, allow_null=True
    )
    services_count = serializers.IntegerField(
        source="program.services_count", read_only=True
    )

    # Cancellation
    cancellation_reason = serializers.CharField(
        source="program.cancellation_reason", read_only=True
    )
    cancelled_at = serializers.DateTimeField(
        source="program.cancelled_at", read_only=True
    )

    class Meta:
        model = TherapyProgram
        fields = [
            "id",
            "program_type",
            "is_complimentary",
            "price",
            "expires_at",
            "sessions_count",
            "sessions_used",
            "services_count",
            "created_at",
            "updated_at",
            "is_active",
            # Cancellation
            "cancellation_reason",
            "cancelled_at",
        ]

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed.")

    def update(self, instance: TherapyProgram, validated_data):
        """Not allowed"""

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "program_type":
            rep["program_type"] = instance.program.get_program_type_display()
        return rep


class CustomerServiceDetailSerializer(BaseModelSerializer):
    program = CustomerTherapyProgramDetailSerializer(
        source="program.therapy_program", read_only=True
    )
    service = ExternalCustomerServiceSerializer(read_only=True)
    sessions_count = serializers.IntegerField(
        source="therapy_service.sessions_count", read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="therapy_service.sessions_used", read_only=True
    )
    redeem_code = serializers.CharField(
        source="therapy_service.redeem_code", read_only=True
    )

    class Meta:
        model = ProgramService
        fields = [
            "program",
            "service",
            "sessions_count",
            "sessions_used",
            "redeem_code",
            "created_at",
            "is_active",
            "cancellation_reason",
            "cancelled_at",
        ]


class CustomerProfileSummarySerializer(BaseModelSerializer):
    programs_count = serializers.IntegerField(read_only=True, default=0)
    programs_expired = serializers.IntegerField(read_only=True, default=0)
    programs_complete = serializers.IntegerField(read_only=True, default=0)
    programs_inactive = serializers.IntegerField(read_only=True, default=0)
    sessions_count = serializers.IntegerField(read_only=True, default=0)
    sessions_used = serializers.IntegerField(read_only=True, default=0)
    sessions_cancelled = serializers.IntegerField(read_only=True, default=0)
    sessions_expired = serializers.IntegerField(read_only=True, default=0)
    centers_count = serializers.IntegerField(read_only=True, default=0)
    external_centers_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "programs_count",
            "programs_expired",
            "programs_inactive",
            "programs_complete",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "sessions_expired",
            "centers_count",
            "external_centers_count",
        ]


class ExternalCustomerAssociateSerializer(
    AssociateSourceMixinSerializer, BaseModelSerializer
):
    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(source="associate.user.email", read_only=True)
    contact_phone = PhoneNumberSerializerField(
        source="associate.contact_phone", read_only=True
    )
    first_name = serializers.CharField(
        source="associate.user.first_name", read_only=True
    )
    last_name = serializers.CharField(source="associate.user.last_name", read_only=True)
    gender = serializers.ChoiceField(
        source="associate.user.gender", choices=Gender.CHOICES, read_only=True
    )

    image = serializers.ImageField(source="associate.user.image", read_only=True)

    role = BaseAssociateRoleSerializer(read_only=True)

    class Meta:
        model = CustomerAssociateAssignment
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "image",
            "role",
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
            "has_verified_badge",
        ]

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep
