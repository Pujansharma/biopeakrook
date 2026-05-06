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
