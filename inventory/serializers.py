from rest_framework import serializers

from accounts.centers.utils.db import generate_room_code, generate_equipment_code
from core.utils.serializers import BaseModelSerializer
from inventory.models import Room, RoomSchedule, Equipment, EquipmentSchedule


class RoomSerializer(BaseModelSerializer):
    class Meta:
        model = Room
        fields = [
            "id",
            "room_type",
            "name",
            "code",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        center = validated_data.get("center_id")
        code = generate_room_code(center)
        validated_data["code"] = code
        return super().create(validated_data)


class RoomScheduleSerializer(BaseModelSerializer):
    class Meta:
        model = RoomSchedule
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "schedule_type",
            "is_active",
            "created_at",
            "updated_at",
        ]


class EquipmentSerializer(BaseModelSerializer):
    room_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = Equipment
        fields = [
            "id",
            "device_type",
            "code",
            "name",
            "serial_number",
            "room",
            "room_id",
            "setup_time",
            "cooldown_time",
            "requires_technician",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "room": {"read_only": True},
        }

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name:
            center_id = self._resolve_center_id()
            if center_id is not None:
                clash = Equipment.objects.filter(center_id=center_id, name__iexact=name)
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError(
                        {"name": ["An equipment with this name already exists."]}
                    )
        return attrs

    def _resolve_center_id(self):
        if self.instance is not None:
            return self.instance.center_id
        request = self.context.get("request")
        if request is None:
            return None
        return getattr(request, "center_id", None)

    @staticmethod
    def validate_room(center_id, room_id):
        if room_id is None:
            return room_id
        room = Room.objects.filter(pk=room_id, center_id=center_id).first()
        if not room:
            raise serializers.ValidationError("Invalid room for this center.")
        return room

    def create(self, validated_data):
        room_id = validated_data.pop("room_id", None)
        center_id = validated_data.get("center_id", None)
        validated_data["room"] = self.validate_room(center_id, room_id)
        validated_data["code"] = generate_equipment_code(center_id)
        return super().create(validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if instance.room:
            rep["room"] = RoomSerializer(instance.room).data
        return rep


class EquipmentScheduleSerializer(BaseModelSerializer):
    class Meta:
        model = EquipmentSchedule
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "schedule_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
