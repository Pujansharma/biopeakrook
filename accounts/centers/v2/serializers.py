from django.db import transaction
from rest_framework import serializers

from accounts.associates.models import AssociateRole
from accounts.associates.utils.roles import resolve_center_roles
from accounts.centers.utils.db import generate_equipment_code, generate_room_code
from accounts.users.serializers import BaseUserSerializer
from core.utils.constants import AppointmentModes
from core.utils.serializers import BaseModelSerializer
from inventory.models import Equipment, EquipmentType, Room, RoomType
from inventory.utils.constants import EquipmentPortability, EquipmentOperationalStatus
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoleRequirement,
    CenterServiceRoomTypeRequirement,
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


def live_required_roles(assignment):
    roles = []
    for requirement in assignment.role_requirements.all():
        if not requirement.is_active:
            continue
        if not requirement.role.is_active:
            continue
        roles.append(requirement.role)
    return roles


def live_required_room_types(assignment):
    room_types = []
    for requirement in assignment.room_type_requirements.all():
        if not requirement.is_active:
            continue
        if not requirement.room_type.is_active:
            continue
        room_types.append(requirement.room_type)
    return room_types


class RequiredRoleIdsField(serializers.ListField):
    def __init__(self, **kwargs):
        kwargs.setdefault("child", serializers.UUIDField())
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_empty", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        return [role.pk for role in live_required_roles(instance)]


class RequiredRoomTypeIdsField(serializers.ListField):
    def __init__(self, **kwargs):
        kwargs.setdefault("child", serializers.UUIDField())
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_empty", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        return [room_type.pk for room_type in live_required_room_types(instance)]


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
        center = self.context["center"]
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name:
            clash = Room.objects.filter(center=center, name__iexact=name)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"name": ["A room with this name already exists."]}
                )
        if self.instance is None and "room_type_id" not in attrs:
            raise serializers.ValidationError(
                {"room_type_id": "This field is required."}
            )
        room_type_id = attrs.pop("room_type_id", None)
        if room_type_id is not None:
            attrs["room_type_ref"] = self._resolve_room_type(center, room_type_id)
        if "equipment_ids" in attrs:
            attrs["equipment_ids"] = self._resolve_equipment_ids(
                center, attrs["equipment_ids"]
            )
        return attrs

    def _resolve_room_type(self, center, room_type_id):
        room_type = RoomType.objects.filter_active(
            pk=room_type_id, center=center
        ).first()
        if not room_type:
            raise serializers.ValidationError(
                {"room_type_id": "Invalid or inactive room type for this center."}
            )
        return room_type

    def _resolve_equipment_ids(self, center, equipment_ids):
        if not equipment_ids:
            return []
        found_ids = list(
            Equipment.objects.filter_active(
                pk__in=equipment_ids, center=center
            ).values_list("pk", flat=True)
        )
        missing_ids = set(equipment_ids) - set(found_ids)
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "equipment_ids": (
                        "Invalid or inactive equipment for this center: "
                        f"{', '.join(str(equipment_id) for equipment_id in missing_ids)}"
                    )
                }
            )
        return found_ids

    def _assign_equipments(self, room, equipment_ids, replace):
        if replace:
            Equipment.objects.filter(room=room).exclude(
                pk__in=equipment_ids
            ).update(room=None)
        if equipment_ids:
            Equipment.objects.filter(pk__in=equipment_ids).update(room=room)

    def create(self, validated_data):
        center = self.context["center"]
        equipment_ids = validated_data.pop("equipment_ids", None)
        validated_data["center"] = center
        validated_data["code"] = generate_room_code(center.pk)
        with transaction.atomic():
            room = super().create(validated_data)
            if equipment_ids is not None:
                self._assign_equipments(room, equipment_ids, replace=False)
        return room

    def update(self, instance, validated_data):
        equipment_ids = validated_data.pop("equipment_ids", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if equipment_ids is not None:
                self._assign_equipments(instance, equipment_ids, replace=True)
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
        center = self.context["center"]
        if self.instance is None and "equipment_type_id" not in attrs:
            raise serializers.ValidationError(
                {"equipment_type_id": "This field is required."}
            )
        equipment_type_id = attrs.pop("equipment_type_id", None)
        if equipment_type_id is not None:
            attrs["equipment_type"] = self._resolve_equipment_type(
                center, equipment_type_id
            )
        if "room_id" in attrs:
            attrs["room"] = self._resolve_room(center, attrs.pop("room_id"))
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name:
            clash = Equipment.objects.filter(center=center, name__iexact=name)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"name": ["An equipment with this name already exists."]}
                )
        return attrs

    def _resolve_equipment_type(self, center, equipment_type_id):
        equipment_type = EquipmentType.objects.filter_active(
            pk=equipment_type_id, center=center
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
        room = Room.objects.filter_active(pk=room_id, center=center).first()
        if not room:
            raise serializers.ValidationError(
                {"room_id": "Invalid or inactive room for this center."}
            )
        return room

    def create(self, validated_data):
        center = self.context["center"]
        validated_data["center"] = center
        validated_data["code"] = generate_equipment_code(center.pk)
        return super().create(validated_data)


class CenterServiceAssignmentV2Serializer(BaseModelSerializer):
    required_roles = serializers.SerializerMethodField()
    required_role_ids = RequiredRoleIdsField()
    required_room_types = serializers.SerializerMethodField()
    required_room_type_ids = RequiredRoomTypeIdsField()
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
            "required_room_type_ids",
            "required_room_types",
            "required_role_ids",
            "required_roles",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_required_roles(self, instance):
        return AssociateRoleNestedSerializer(
            live_required_roles(instance), many=True
        ).data

    def get_required_room_types(self, instance):
        return RoomTypeNestedSerializer(
            live_required_room_types(instance), many=True
        ).data

    def validate(self, attrs):
        if "required_role_ids" in attrs:
            role_ids = attrs.get("required_role_ids") or []
            attrs["required_role_ids"] = resolve_center_roles(
                self.context["center"],
                role_ids,
                field_name="required_role_ids",
            )
        if "required_room_type_ids" in attrs:
            room_type_ids = attrs.get("required_room_type_ids") or []
            attrs["required_room_type_ids"] = self._resolve_room_types(
                self.context["center"], room_type_ids
            )
        return attrs

    def _resolve_room_types(self, center, room_type_ids):
        if not room_type_ids:
            return []
        room_types = list(
            RoomType.objects.filter_active(center=center, pk__in=room_type_ids)
        )
        found_ids = {room_type.pk for room_type in room_types}
        missing_ids = set(room_type_ids) - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "required_room_type_ids": (
                        "Invalid or inactive room types for this center: "
                        f"{', '.join(str(room_type_id) for room_type_id in missing_ids)}"
                    )
                }
            )
        return room_types

    def update(self, instance, validated_data):
        roles = validated_data.pop("required_role_ids", None)
        room_types = validated_data.pop("required_room_type_ids", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if roles is not None:
                CenterServiceRoleRequirement.objects.filter(assignment=instance).delete()
                CenterServiceRoleRequirement.objects.bulk_create(
                    [
                        CenterServiceRoleRequirement(
                            assignment=instance,
                            role_id=role.pk,
                        )
                        for role in roles
                    ]
                )
            if room_types is not None:
                CenterServiceRoomTypeRequirement.objects.filter(
                    assignment=instance
                ).delete()
                CenterServiceRoomTypeRequirement.objects.bulk_create(
                    [
                        CenterServiceRoomTypeRequirement(
                            assignment=instance,
                            room_type_id=room_type.pk,
                        )
                        for room_type in room_types
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
