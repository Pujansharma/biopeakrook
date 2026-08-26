from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from accounts.associates.models import AssociateRole
from accounts.centers.utils.db import generate_equipment_code, generate_room_code
from accounts.users.serializers import BaseUserSerializer
from core.utils.constants import AppointmentModes
from core.utils.serializers import BaseModelSerializer
from inventory.models import Equipment, EquipmentType, Room, RoomType
from inventory.utils.constants import EquipmentPortability, EquipmentOperationalStatus
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoleRequirement,
    Service,
)


class RoomTypeNestedSerializer(BaseModelSerializer):
    class Meta:
        model = RoomType
        fields = ["id", "name", "is_active"]


class EquipmentTypeNestedSerializer(BaseModelSerializer):
    portability_code = serializers.CharField(source="portability", read_only=True)

    class Meta:
        model = EquipmentType
        fields = [
            "id",
            "name",
            "description",
            "portability",
            "portability_code",
            "is_active",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["portability"] = instance.portability
        return representation


class AssociateRoleNestedSerializer(BaseModelSerializer):
    class Meta:
        model = AssociateRole
        fields = ["id", "name", "is_active"]


class RoomTypeV2Serializer(BaseModelSerializer):
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = RoomType
        fields = [
            "id",
            "name",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        center = self.context["center"]
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name is not None:
            existing = RoomType.objects.filter(center=center, name=name)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"name": "A room type with this name already exists for this center."}
                )
        return attrs


class EquipmentTypeV2Serializer(BaseModelSerializer):
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)
    portability = serializers.ChoiceField(
        choices=EquipmentPortability, required=False, default=EquipmentPortability.FIXED
    )
    portability_code = serializers.CharField(source="portability", read_only=True)

    class Meta:
        model = EquipmentType
        fields = [
            "id",
            "name",
            "description",
            "portability",
            "portability_code",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        center = self.context["center"]
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name is not None:
            existing = EquipmentType.objects.filter(center=center, name=name)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {
                        "name": (
                            "An equipment type with this name already exists "
                            "for this center."
                        )
                    }
                )
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["portability"] = instance.portability
        return representation


class RoomNestedSerializer(BaseModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "code", "is_active"]


class RoomEquipmentNestedSerializer(BaseModelSerializer):
    class Meta:
        model = Equipment
        fields = ["id", "name", "code", "is_active"]


class RoomV2Serializer(BaseModelSerializer):
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)
    room_type_id = serializers.UUIDField(write_only=True, required=False)
    room_type = RoomTypeNestedSerializer(source="room_type_ref", read_only=True)
    capacity = serializers.IntegerField(required=False, min_value=1, default=1)
    floor = serializers.CharField(required=False, allow_blank=True, default="")
    equipment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    equipments = RoomEquipmentNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "name",
            "code",
            "room_type_id",
            "room_type",
            "capacity",
            "floor",
            "equipment_ids",
            "equipments",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"code": {"read_only": True}}

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        if self.instance is None and "room_type_id" not in attrs:
            raise serializers.ValidationError(
                {"room_type_id": "This field is required."}
            )
        return attrs

    def _resolve_room_type(self, center, room_type_id):
        room_type = RoomType.objects.filter(
            pk=room_type_id, center=center, is_active=True
        ).first()
        if not room_type:
            raise serializers.ValidationError(
                {"room_type_id": "Invalid or inactive room type for this center."}
            )
        return room_type

    def _resolve_equipments(self, center, equipment_ids):
        if not equipment_ids:
            return []
        equipments = list(
            Equipment.objects.filter(
                pk__in=equipment_ids, center=center, is_active=True
            )
        )
        found_ids = {equipment.pk for equipment in equipments}
        missing_ids = set(equipment_ids) - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "equipment_ids": (
                        "Invalid or inactive equipment for this center: "
                        f"{', '.join(str(equipment_id) for equipment_id in missing_ids)}"
                    )
                }
            )
        return equipments

    def _assign_equipments(self, room, equipments, replace):
        if replace:
            Equipment.objects.filter(room=room).exclude(
                pk__in=[equipment.pk for equipment in equipments]
            ).update(room=None)
        if equipments:
            Equipment.objects.filter(
                pk__in=[equipment.pk for equipment in equipments]
            ).update(room=room)

    def create(self, validated_data):
        center = self.context["center"]
        room_type_id = validated_data.pop("room_type_id")
        equipment_ids = validated_data.pop("equipment_ids", None)
        room_type = self._resolve_room_type(center, room_type_id)
        equipments = (
            self._resolve_equipments(center, equipment_ids)
            if equipment_ids is not None
            else []
        )
        validated_data["center"] = center
        validated_data["room_type_ref"] = room_type
        validated_data["code"] = generate_room_code(center.pk)
        with transaction.atomic():
            room = super().create(validated_data)
            if equipment_ids is not None:
                self._assign_equipments(room, equipments, replace=False)
        return room

    def update(self, instance, validated_data):
        center = self.context["center"]
        room_type_id = validated_data.pop("room_type_id", None)
        equipment_ids = validated_data.pop("equipment_ids", None)
        if room_type_id is not None:
            instance.room_type_ref = self._resolve_room_type(center, room_type_id)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if equipment_ids is not None:
                equipments = self._resolve_equipments(center, equipment_ids)
                self._assign_equipments(instance, equipments, replace=True)
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # BaseModelSerializer rewrites choice fields via get_<name>_display;
        # legacy CharField room_type would clobber the nested room_type_ref payload.
        if instance.room_type_ref_id:
            representation["room_type"] = RoomTypeNestedSerializer(
                instance.room_type_ref
            ).data
        else:
            representation["room_type"] = None
        return representation


class EquipmentV2Serializer(BaseModelSerializer):
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)
    equipment_type_id = serializers.UUIDField(write_only=True, required=False)
    equipment_type = EquipmentTypeNestedSerializer(read_only=True)
    room_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True, default=None
    )
    room = RoomNestedSerializer(read_only=True)
    serial_number = serializers.CharField(required=False, allow_blank=True, default="")
    setup_time = serializers.IntegerField(required=False, min_value=0, default=0)
    cooldown_time = serializers.IntegerField(required=False, min_value=0, default=0)
    requires_technician = serializers.BooleanField(required=False, default=False)
    operational_status = serializers.ChoiceField(
        choices=EquipmentOperationalStatus,
        required=False,
        default=EquipmentOperationalStatus.OPERATIONAL,
    )
    operational_status_code = serializers.CharField(
        source="operational_status", read_only=True
    )
    is_in_maintenance = serializers.SerializerMethodField(read_only=True)
    is_downtime = serializers.SerializerMethodField(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["operational_status"].read_only = True

    class Meta:
        model = Equipment
        fields = [
            "id",
            "name",
            "code",
            "equipment_type_id",
            "equipment_type",
            "room_id",
            "room",
            "serial_number",
            "setup_time",
            "cooldown_time",
            "requires_technician",
            "operational_status",
            "operational_status_code",
            "is_in_maintenance",
            "is_downtime",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"code": {"read_only": True}}

    def get_is_in_maintenance(self, instance):
        return instance.operational_status == EquipmentOperationalStatus.MAINTENANCE

    def get_is_downtime(self, instance):
        return instance.operational_status == EquipmentOperationalStatus.DOWNTIME

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["operational_status"] = instance.operational_status
        return representation

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        if self.instance is None and "equipment_type_id" not in attrs:
            raise serializers.ValidationError(
                {"equipment_type_id": "This field is required."}
            )
        return attrs

    def _resolve_equipment_type(self, center, equipment_type_id):
        equipment_type = EquipmentType.objects.filter(
            pk=equipment_type_id, center=center, is_active=True
        ).first()
        if not equipment_type:
            raise serializers.ValidationError(
                {
                    "equipment_type_id": (
                        "Invalid or inactive equipment type for this center."
                    )
                }
            )
        return equipment_type

    def _resolve_room(self, center, room_id):
        if room_id is None:
            return None
        room = Room.objects.filter(pk=room_id, center=center, is_active=True).first()
        if not room:
            raise serializers.ValidationError(
                {"room_id": "Invalid or inactive room for this center."}
            )
        return room

    def create(self, validated_data):
        center = self.context["center"]
        equipment_type_id = validated_data.pop("equipment_type_id")
        room_id = validated_data.pop("room_id", None)
        validated_data["center"] = center
        validated_data["equipment_type"] = self._resolve_equipment_type(
            center, equipment_type_id
        )
        validated_data["room"] = self._resolve_room(center, room_id)
        validated_data["code"] = generate_equipment_code(center.pk)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        center = self.context["center"]
        equipment_type_id = validated_data.pop("equipment_type_id", None)
        if equipment_type_id is not None:
            instance.equipment_type = self._resolve_equipment_type(
                center, equipment_type_id
            )
        if "room_id" in validated_data:
            room_id = validated_data.pop("room_id")
            instance.room = self._resolve_room(center, room_id)
        return super().update(instance, validated_data)


class CenterServiceAssignmentV2Serializer(BaseModelSerializer):
    required_roles = AssociateRoleNestedSerializer(many=True, read_only=True)
    required_role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        allow_null=True,
    )
    modality = serializers.ChoiceField(
        choices=AppointmentModes.choices, required=False, default=AppointmentModes.BOTH
    )
    modality_code = serializers.CharField(source="modality", read_only=True)
    duration = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    buffer_before = serializers.IntegerField(required=False, min_value=0)
    buffer_after = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = CenterServiceAssignment
        fields = [
            "id",
            "duration",
            "buffer_before",
            "buffer_after",
            "modality",
            "modality_code",
            "required_room_type_id",
            "required_room_type",
            "required_equipment_type_id",
            "required_equipment_type",
            "required_role_ids",
            "required_roles",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "required_room_type": {"read_only": True},
            "required_equipment_type": {"read_only": True},
        }

    def get_fields(self):
        fields = super().get_fields()
        center = self.context.get("center")
        room_type_queryset = RoomType.objects.none()
        equipment_type_queryset = EquipmentType.objects.none()
        if center is not None:
            room_type_queryset = RoomType.objects.filter(center=center, is_active=True)
            equipment_type_queryset = EquipmentType.objects.filter(
                center=center, is_active=True
            )

        fields["required_room_type"] = RoomTypeNestedSerializer(read_only=True)
        fields["required_equipment_type"] = EquipmentTypeNestedSerializer(read_only=True)
        fields["required_room_type_id"] = serializers.PrimaryKeyRelatedField(
            source="required_room_type",
            queryset=room_type_queryset,
            write_only=True,
            required=False,
            allow_null=True,
            error_messages={
                "does_not_exist": "Invalid or inactive room type for this center."
            },
        )
        fields["required_equipment_type_id"] = serializers.PrimaryKeyRelatedField(
            source="required_equipment_type",
            queryset=equipment_type_queryset,
            write_only=True,
            required=False,
            allow_null=True,
            error_messages={
                "does_not_exist": (
                    "Invalid or inactive equipment type for this center."
                )
            },
        )
        return fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["modality"] = instance.modality
        role_requirements = list(
            instance.role_requirements.filter(is_active=True).select_related("role")
        )
        representation["required_role_ids"] = [
            requirement.role_id for requirement in role_requirements
        ]
        representation["required_roles"] = AssociateRoleNestedSerializer(
            [requirement.role for requirement in role_requirements], many=True
        ).data
        return representation

    def _resolve_roles(self, center, role_ids):
        if not role_ids:
            return []
        roles = list(
            AssociateRole.objects.filter(
                Q(pk__in=role_ids)
                & (Q(is_system=True) | Q(center=center))
                & Q(is_active=True)
            )
        )
        found_ids = {role.pk for role in roles}
        missing_ids = set(role_ids) - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "required_role_ids": (
                        "Invalid or inactive roles for this center: "
                        f"{', '.join(str(role_id) for role_id in missing_ids)}"
                    )
                }
            )
        return roles

    def update(self, instance, validated_data):
        center = self.context["center"]
        role_ids_provided = "required_role_ids" in validated_data
        role_ids = validated_data.pop("required_role_ids", None)
        if role_ids_provided and role_ids is None:
            role_ids = []

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if role_ids_provided:
                roles = self._resolve_roles(center, role_ids)
                CenterServiceRoleRequirement.objects.filter(assignment=instance).delete()
                CenterServiceRoleRequirement.objects.bulk_create(
                    [
                        CenterServiceRoleRequirement(assignment=instance, role=role)
                        for role in roles
                    ]
                )
        return instance


class CenterServiceV2Serializer(BaseModelSerializer):
    service_category_code = serializers.CharField(
        source="service_category", read_only=True
    )
    assignment = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "service_category",
            "service_category_code",
            "image",
            "is_global",
            "is_active",
            "assignment",
            "created_at",
            "updated_at",
        ]

    def get_assignment(self, instance):
        assignments = getattr(instance, "center_assignments", None)
        if assignments is None:
            return None
        assignment_list = list(assignments.all())
        if not assignment_list:
            return None
        return CenterServiceAssignmentV2Serializer(
            assignment_list[0], context=self.context
        ).data
