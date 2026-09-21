import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.associates.models import Associate
from accounts.centers.models import Center, CenterClosure, CenterOperatingHour
from accounts.centers.utils.constants import CenterClosureType
from accounts.users.serializers import BaseUserSerializer
from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    AssociateRosterEntry,
    CareTeamAvailabilityBlock,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.utils.constants import AvailabilityOrigin, LeaveScope
from appointments.utils.operating_hours import (
    assert_operating_hours_cover_roster,
    assert_roster_within_operating_hours,
)
from appointments.utils.overlap import (
    assert_associate_block_no_overlap,
    assert_associate_leave_no_overlap,
    assert_care_team_block_no_overlap,
    assert_equipment_block_no_overlap,
    assert_equipment_downtime_no_overlap,
    assert_room_block_no_overlap,
    assert_room_downtime_no_overlap,
    raise_if_care_team_one_off_overlap_integrity,
    validate_same_day_time_window,
)
from core.utils.constants import AppointmentDays
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from integrations.communications import (
    schedule_queue_associate_block_sync,
    schedule_queue_associate_leave_sync,
)
from inventory.models import Equipment, Room


class AssociateNestedSerializer(BaseModelSerializer):
    class Meta:
        model = Associate
        fields = ["user_id", "is_active"]


class RoomNestedSerializer(BaseModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "code", "is_active"]


class EquipmentNestedSerializer(BaseModelSerializer):
    class Meta:
        model = Equipment
        fields = ["id", "name", "code", "is_active"]


def validate_recurring_block_fields(data, errors):
    if not data.get("day_of_week"):
        errors["day_of_week"] = ["Required for recurring blocks."]
    if not data.get("recurring_start_time"):
        errors["recurring_start_time"] = ["Required for recurring blocks."]
    if not data.get("recurring_end_time"):
        errors["recurring_end_time"] = ["Required for recurring blocks."]
    if not data.get("effective_from"):
        errors["effective_from"] = ["Required for recurring blocks."]


def validate_recurring_block_create_fields(data, errors):
    days_of_week = data.get("days_of_week")
    if not days_of_week:
        errors["days_of_week"] = ["Required for recurring blocks."]
    elif len(days_of_week) != len(set(days_of_week)):
        errors["days_of_week"] = ["Duplicate days are not allowed."]
    if not data.get("recurring_start_time"):
        errors["recurring_start_time"] = ["Required for recurring blocks."]
    if not data.get("recurring_end_time"):
        errors["recurring_end_time"] = ["Required for recurring blocks."]
    if (
        data.get("recurring_start_time")
        and data.get("recurring_end_time")
        and data["recurring_start_time"] >= data["recurring_end_time"]
    ):
        errors["recurring_end_time"] = ["Must be after recurring_start_time."]
    if not data.get("effective_from"):
        errors["effective_from"] = ["Required for recurring blocks."]


def validate_one_off_block_fields(data, errors):
    if not data.get("start_datetime"):
        errors["start_datetime"] = ["Required for one-off blocks."]
    if not data.get("end_datetime"):
        errors["end_datetime"] = ["Required for one-off blocks."]
    if (
        data.get("start_datetime")
        and data.get("end_datetime")
        and data["start_datetime"] >= data["end_datetime"]
    ):
        errors["end_datetime"] = ["Must be after start_datetime."]


def validate_resource_one_off_day_fields(data, errors):
    if not data.get("date"):
        errors["date"] = ["Required for one-off blocks."]
    if not data.get("start_time"):
        errors["start_time"] = ["Required for one-off blocks."]
    if not data.get("end_time"):
        errors["end_time"] = ["Required for one-off blocks."]
    validate_same_day_time_window(
        data.get("start_time"), data.get("end_time"), errors
    )


def merge_block_validation_data(data, instance):
    return {
        "is_recurring": data.get(
            "is_recurring",
            getattr(instance, "is_recurring", False) if instance else False,
        ),
        "start_datetime": data.get(
            "start_datetime",
            getattr(instance, "start_datetime", None) if instance else None,
        ),
        "end_datetime": data.get(
            "end_datetime",
            getattr(instance, "end_datetime", None) if instance else None,
        ),
        "day_of_week": data.get(
            "day_of_week",
            getattr(instance, "day_of_week", None) if instance else None,
        ),
        "recurring_start_time": data.get(
            "recurring_start_time",
            getattr(instance, "recurring_start_time", None) if instance else None,
        ),
        "recurring_end_time": data.get(
            "recurring_end_time",
            getattr(instance, "recurring_end_time", None) if instance else None,
        ),
        "effective_from": data.get(
            "effective_from",
            getattr(instance, "effective_from", None) if instance else None,
        ),
        "effective_until": data.get(
            "effective_until",
            getattr(instance, "effective_until", None) if instance else None,
        ),
        "is_active": data.get(
            "is_active",
            getattr(instance, "is_active", True) if instance else True,
        ),
    }


def merge_resource_block_validation_data(data, instance):
    return {
        "is_recurring": data.get(
            "is_recurring",
            getattr(instance, "is_recurring", False) if instance else False,
        ),
        "date": data.get(
            "date",
            getattr(instance, "date", None) if instance else None,
        ),
        "start_time": data.get(
            "start_time",
            getattr(instance, "start_time", None) if instance else None,
        ),
        "end_time": data.get(
            "end_time",
            getattr(instance, "end_time", None) if instance else None,
        ),
        "day_of_week": data.get(
            "day_of_week",
            getattr(instance, "day_of_week", None) if instance else None,
        ),
        "recurring_start_time": data.get(
            "recurring_start_time",
            getattr(instance, "recurring_start_time", None) if instance else None,
        ),
        "recurring_end_time": data.get(
            "recurring_end_time",
            getattr(instance, "recurring_end_time", None) if instance else None,
        ),
        "effective_from": data.get(
            "effective_from",
            getattr(instance, "effective_from", None) if instance else None,
        ),
        "effective_until": data.get(
            "effective_until",
            getattr(instance, "effective_until", None) if instance else None,
        ),
        "is_active": data.get(
            "is_active",
            getattr(instance, "is_active", True) if instance else True,
        ),
    }


def create_associate_availability_block(
    center,
    associate,
    created_by,
    is_recurring,
    start_datetime,
    end_datetime,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    reason,
    is_active,
    google_event_id="",
    origin=AvailabilityOrigin.MANUAL,
    series_id=None,
):
    return AssociateAvailabilityBlock.objects.create(
        center=center,
        associate=associate,
        created_by=created_by,
        is_recurring=is_recurring,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        day_of_week=day_of_week,
        recurring_start_time=recurring_start_time,
        recurring_end_time=recurring_end_time,
        effective_from=effective_from,
        effective_until=effective_until,
        reason=reason,
        is_active=is_active,
        google_event_id=google_event_id,
        origin=origin,
        series_id=series_id,
    )


def create_room_availability_block(
    room,
    created_by,
    is_recurring,
    date,
    start_time,
    end_time,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    reason,
    is_active,
):
    return RoomAvailabilityBlock.objects.create(
        room=room,
        created_by=created_by,
        is_recurring=is_recurring,
        date=date,
        start_time=start_time,
        end_time=end_time,
        day_of_week=day_of_week,
        recurring_start_time=recurring_start_time,
        recurring_end_time=recurring_end_time,
        effective_from=effective_from,
        effective_until=None,
        reason=reason,
        is_active=is_active,
    )


def create_equipment_availability_block(
    equipment,
    created_by,
    is_recurring,
    date,
    start_time,
    end_time,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    reason,
    is_active,
):
    return EquipmentAvailabilityBlock.objects.create(
        equipment=equipment,
        created_by=created_by,
        is_recurring=is_recurring,
        date=date,
        start_time=start_time,
        end_time=end_time,
        day_of_week=day_of_week,
        recurring_start_time=recurring_start_time,
        recurring_end_time=recurring_end_time,
        effective_from=effective_from,
        effective_until=None,
        reason=reason,
        is_active=is_active,
    )


def reject_effective_until(initial_data):
    if "effective_until" in initial_data:
        raise serializers.ValidationError(
            {
                "effective_until": [
                    "Not supported. Deactivate the block with is_active=false."
                ]
            }
        )


def reject_google_origin_edit(instance):
    if instance is not None and instance.origin == AvailabilityOrigin.GOOGLE:
        raise serializers.ValidationError(
            "This entry is synced from Google Calendar. Change it in Google Calendar."
        )


def clear_effective_until(instance):
    if instance.effective_until is not None:
        instance.effective_until = None
        instance.save(update_fields=["effective_until", "updated_at"])
    return instance

class AssociateRosterEntrySerializer(BaseModelSerializer):
    associate_id = serializers.UUIDField(source="associate.pk", read_only=True)
    center_id = serializers.UUIDField(source="center.pk", read_only=True)
    day_of_week_code = serializers.CharField(source="day_of_week", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = AssociateRosterEntry
        fields = [
            "id",
            "center_id",
            "associate_id",
            "day_of_week",
            "day_of_week_code",
            "start_time",
            "end_time",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        errors = {}
        start_time = data.get("start_time") or getattr(
            self.instance, "start_time", None
        )
        end_time = data.get("end_time") or getattr(self.instance, "end_time", None)
        if start_time and end_time and start_time >= end_time:
            errors["end_time"] = ["Must be after start_time."]
        if errors:
            raise serializers.ValidationError(errors)
        return data


class AssociateAvailabilityBlockSerializer(BaseModelSerializer):
    associate_id = serializers.UUIDField(source="associate.pk", read_only=True)
    center_id = serializers.UUIDField(source="center.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = AssociateAvailabilityBlock
        fields = [
            "id",
            "center_id",
            "associate_id",
            "is_recurring",
            "start_datetime",
            "end_datetime",
            "day_of_week",
            "recurring_start_time",
            "recurring_end_time",
            "effective_from",
            "reason",
            "origin",
            "google_event_id",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "origin", "google_event_id", "created_at", "updated_at"]

    def validate(self, data):
        reject_google_origin_edit(self.instance)
        if "effective_until" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "effective_until": [
                        "Not supported. Deactivate the block with is_active=false."
                    ]
                }
            )
        merged = merge_block_validation_data(data, self.instance)
        merged["effective_until"] = None
        errors = {}
        if merged["is_recurring"]:
            validate_recurring_block_fields(merged, errors)
        else:
            validate_one_off_block_fields(merged, errors)
        if errors:
            raise serializers.ValidationError(errors)
        if self.instance is not None and merged["is_active"]:
            assert_associate_block_no_overlap(
                self.instance.center,
                self.instance.associate,
                merged["is_recurring"],
                merged["start_datetime"],
                merged["end_datetime"],
                merged["day_of_week"],
                merged["recurring_start_time"],
                merged["recurring_end_time"],
                merged["effective_from"],
                None,
                exclude_id=self.instance.pk,
            )
        return data

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if instance.effective_until is not None:
            instance.effective_until = None
            instance.save(update_fields=["effective_until", "updated_at"])
        if instance.origin == AvailabilityOrigin.MANUAL:
            schedule_queue_associate_block_sync(
                block=instance, series_id=instance.series_id
            )
        return instance


class AssociateAvailabilityBlockCreateSerializer(BaseSerializer):
    is_recurring = serializers.BooleanField(default=False)
    start_datetime = serializers.DateTimeField(required=False, allow_null=True)
    end_datetime = serializers.DateTimeField(required=False, allow_null=True)
    days_of_week = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        allow_empty=False,
        required=False,
    )
    recurring_start_time = serializers.TimeField(required=False, allow_null=True)
    recurring_end_time = serializers.TimeField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        if "effective_until" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "effective_until": [
                        "Not supported. Deactivate the block with is_active=false."
                    ]
                }
            )
        is_recurring = data.get("is_recurring", False)
        errors = {}
        if is_recurring:
            validate_recurring_block_create_fields(data, errors)
        else:
            if data.get("days_of_week"):
                errors["days_of_week"] = ["Not allowed for one-off blocks."]
            validate_one_off_block_fields(data, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        center = validated_data["center"]
        associate = validated_data["associate"]
        created_by = validated_data.get("created_by")
        is_recurring = validated_data.get("is_recurring", False)
        reason = validated_data.get("reason", "")
        is_active = validated_data.get("is_active", True)
        series_id = uuid.uuid7() if is_recurring else None
        results = []
        with transaction.atomic():
            if is_recurring:
                for day_of_week in validated_data["days_of_week"]:
                    if is_active:
                        assert_associate_block_no_overlap(
                            center,
                            associate,
                            True,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                        )
                    results.append(
                        create_associate_availability_block(
                            center,
                            associate,
                            created_by,
                            True,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                            reason,
                            is_active,
                            series_id=series_id,
                        )
                    )
            else:
                if is_active:
                    assert_associate_block_no_overlap(
                        center,
                        associate,
                        False,
                        validated_data.get("start_datetime"),
                        validated_data.get("end_datetime"),
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                results.append(
                    create_associate_availability_block(
                        center,
                        associate,
                        created_by,
                        False,
                        validated_data.get("start_datetime"),
                        validated_data.get("end_datetime"),
                        None,
                        None,
                        None,
                        None,
                        None,
                        reason,
                        is_active,
                    )
                )
        if results:
            schedule_queue_associate_block_sync(
                block=results[0], series_id=series_id
            )
        return results


def create_care_team_availability_block(
    center,
    care_team,
    created_by,
    is_recurring,
    start_datetime,
    end_datetime,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    reason,
    is_active,
):
    try:
        return CareTeamAvailabilityBlock.objects.create(
            center=center,
            care_team=care_team,
            created_by=created_by,
            is_recurring=is_recurring,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            day_of_week=day_of_week,
            recurring_start_time=recurring_start_time,
            recurring_end_time=recurring_end_time,
            effective_from=effective_from,
            effective_until=effective_until,
            reason=reason,
            is_active=is_active,
        )
    except IntegrityError as error:
        raise_if_care_team_one_off_overlap_integrity(error)


class CareTeamAvailabilityBlockSerializer(BaseModelSerializer):
    care_team_id = serializers.UUIDField(source="care_team.pk", read_only=True)
    center_id = serializers.UUIDField(source="center.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = CareTeamAvailabilityBlock
        fields = [
            "id",
            "center_id",
            "care_team_id",
            "is_recurring",
            "start_datetime",
            "end_datetime",
            "day_of_week",
            "recurring_start_time",
            "recurring_end_time",
            "effective_from",
            "reason",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        if "effective_until" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "effective_until": [
                        "Not supported. Deactivate the block with is_active=false."
                    ]
                }
            )
        merged = merge_block_validation_data(data, self.instance)
        merged["effective_until"] = None
        errors = {}
        if merged["is_recurring"]:
            validate_recurring_block_fields(merged, errors)
        else:
            validate_one_off_block_fields(merged, errors)
        if errors:
            raise serializers.ValidationError(errors)
        if self.instance is not None and merged["is_active"]:
            assert_care_team_block_no_overlap(
                self.instance.center,
                self.instance.care_team,
                merged["is_recurring"],
                merged["start_datetime"],
                merged["end_datetime"],
                merged["day_of_week"],
                merged["recurring_start_time"],
                merged["recurring_end_time"],
                merged["effective_from"],
                None,
                exclude_id=self.instance.pk,
            )
        return data

    def update(self, instance, validated_data):
        try:
            instance = super().update(instance, validated_data)
        except IntegrityError as error:
            raise_if_care_team_one_off_overlap_integrity(error)
        if instance.effective_until is not None:
            instance.effective_until = None
            instance.save(update_fields=["effective_until", "updated_at"])
        return instance


class CareTeamAvailabilityBlockCreateSerializer(BaseSerializer):
    is_recurring = serializers.BooleanField(default=False)
    start_datetime = serializers.DateTimeField(required=False, allow_null=True)
    end_datetime = serializers.DateTimeField(required=False, allow_null=True)
    days_of_week = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        allow_empty=False,
        required=False,
    )
    recurring_start_time = serializers.TimeField(required=False, allow_null=True)
    recurring_end_time = serializers.TimeField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        if "effective_until" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "effective_until": [
                        "Not supported. Deactivate the block with is_active=false."
                    ]
                }
            )
        is_recurring = data.get("is_recurring", False)
        errors = {}
        if is_recurring:
            validate_recurring_block_create_fields(data, errors)
        else:
            if data.get("days_of_week"):
                errors["days_of_week"] = ["Not allowed for one-off blocks."]
            validate_one_off_block_fields(data, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        center = validated_data["center"]
        care_team = validated_data["care_team"]
        created_by = validated_data.get("created_by")
        is_recurring = validated_data.get("is_recurring", False)
        reason = validated_data.get("reason", "")
        is_active = validated_data.get("is_active", True)
        results = []
        with transaction.atomic():
            if is_recurring:
                for day_of_week in validated_data["days_of_week"]:
                    if is_active:
                        assert_care_team_block_no_overlap(
                            center,
                            care_team,
                            True,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                        )
                    results.append(
                        create_care_team_availability_block(
                            center,
                            care_team,
                            created_by,
                            True,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                            reason,
                            is_active,
                        )
                    )
            else:
                if is_active:
                    assert_care_team_block_no_overlap(
                        center,
                        care_team,
                        False,
                        validated_data.get("start_datetime"),
                        validated_data.get("end_datetime"),
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                results.append(
                    create_care_team_availability_block(
                        center,
                        care_team,
                        created_by,
                        False,
                        validated_data.get("start_datetime"),
                        validated_data.get("end_datetime"),
                        None,
                        None,
                        None,
                        None,
                        None,
                        reason,
                        is_active,
                    )
                )
        return results


def resolve_associate_leave_center(scope, center):
    if scope == LeaveScope.ALL_CENTERS:
        return None
    return center


class AssociateLeaveSerializer(BaseModelSerializer):
    associate_id = serializers.UUIDField(source="associate.pk", read_only=True)
    center_id = serializers.UUIDField(source="center.pk", read_only=True, allow_null=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = AssociateLeave
        fields = [
            "id",
            "associate_id",
            "scope",
            "center_id",
            "start_datetime",
            "end_datetime",
            "reason",
            "origin",
            "google_event_id",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["origin", "google_event_id"]

    def validate(self, data):
        reject_google_origin_edit(self.instance)
        scope = data.get("scope", getattr(self.instance, "scope", LeaveScope.CENTER))
        associate = self.context.get("associate") or getattr(
            self.instance, "associate", None
        )
        center = resolve_associate_leave_center(scope, self.context.get("center"))
        if scope == LeaveScope.CENTER and center is None:
            center = getattr(self.instance, "center", None)
        errors = {}
        if scope == LeaveScope.CENTER and center is None:
            errors["center"] = ["Required when scope is center."]
        start_datetime = data.get("start_datetime") or getattr(
            self.instance, "start_datetime", None
        )
        end_datetime = data.get("end_datetime") or getattr(
            self.instance, "end_datetime", None
        )
        if start_datetime and end_datetime and start_datetime >= end_datetime:
            errors["end_datetime"] = ["Must be after start_datetime."]
        if errors:
            raise serializers.ValidationError(errors)
        is_active = data.get(
            "is_active", getattr(self.instance, "is_active", True)
        )
        if is_active and associate and start_datetime and end_datetime:
            exclude_id = self.instance.pk if self.instance is not None else None
            assert_associate_leave_no_overlap(
                associate,
                scope,
                center,
                start_datetime,
                end_datetime,
                exclude_id=exclude_id,
            )
        return data

    def create(self, validated_data):
        leave = AssociateLeave.objects.create(
            associate=validated_data["associate"],
            scope=validated_data.get("scope", LeaveScope.CENTER),
            center=validated_data.get("center"),
            start_datetime=validated_data["start_datetime"],
            end_datetime=validated_data["end_datetime"],
            reason=validated_data.get("reason", ""),
            is_active=validated_data.get("is_active", True),
            created_by=validated_data.get("created_by"),
            origin=AvailabilityOrigin.MANUAL,
        )
        schedule_queue_associate_leave_sync(leave)
        return leave

    def update(self, instance, validated_data):
        scope = validated_data.get("scope", instance.scope)
        validated_data["center"] = resolve_associate_leave_center(
            scope, self.context.get("center")
        )
        instance = super().update(instance, validated_data)
        if instance.origin == AvailabilityOrigin.MANUAL:
            schedule_queue_associate_leave_sync(instance)
        return instance


class RoomAvailabilityBlockSerializer(BaseModelSerializer):
    room_id = serializers.UUIDField(source="room.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = RoomAvailabilityBlock
        fields = [
            "id",
            "room_id",
            "is_recurring",
            "date",
            "start_time",
            "end_time",
            "day_of_week",
            "recurring_start_time",
            "recurring_end_time",
            "effective_from",
            "reason",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        reject_effective_until(self.initial_data)
        merged = merge_resource_block_validation_data(data, self.instance)
        merged["effective_until"] = None
        errors = {}
        if merged["is_recurring"]:
            validate_recurring_block_fields(merged, errors)
        else:
            validate_resource_one_off_day_fields(merged, errors)
        if errors:
            raise serializers.ValidationError(errors)
        if self.instance is not None and merged["is_active"]:
            assert_room_block_no_overlap(
                self.instance.room,
                merged["is_recurring"],
                merged["date"],
                merged["start_time"],
                merged["end_time"],
                merged["day_of_week"],
                merged["recurring_start_time"],
                merged["recurring_end_time"],
                merged["effective_from"],
                None,
                exclude_id=self.instance.pk,
            )
        return data

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        return clear_effective_until(instance)


class RoomAvailabilityBlockCreateSerializer(BaseSerializer):
    is_recurring = serializers.BooleanField(default=False)
    date = serializers.DateField(required=False, allow_null=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    days_of_week = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        allow_empty=False,
        required=False,
    )
    recurring_start_time = serializers.TimeField(required=False, allow_null=True)
    recurring_end_time = serializers.TimeField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        reject_effective_until(self.initial_data)
        is_recurring = data.get("is_recurring", False)
        errors = {}
        if is_recurring:
            validate_recurring_block_create_fields(data, errors)
        else:
            if data.get("days_of_week"):
                errors["days_of_week"] = ["Not allowed for one-off blocks."]
            validate_resource_one_off_day_fields(data, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        room = validated_data["room"]
        created_by = validated_data.get("created_by")
        is_recurring = validated_data.get("is_recurring", False)
        reason = validated_data.get("reason", "")
        is_active = validated_data.get("is_active", True)
        results = []
        with transaction.atomic():
            if is_recurring:
                for day_of_week in validated_data["days_of_week"]:
                    if is_active:
                        assert_room_block_no_overlap(
                            room,
                            True,
                            None,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                        )
                    results.append(
                        create_room_availability_block(
                            room,
                            created_by,
                            True,
                            None,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            reason,
                            is_active,
                        )
                    )
            else:
                if is_active:
                    assert_room_block_no_overlap(
                        room,
                        False,
                        validated_data.get("date"),
                        validated_data.get("start_time"),
                        validated_data.get("end_time"),
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                results.append(
                    create_room_availability_block(
                        room,
                        created_by,
                        False,
                        validated_data.get("date"),
                        validated_data.get("start_time"),
                        validated_data.get("end_time"),
                        None,
                        None,
                        None,
                        None,
                        reason,
                        is_active,
                    )
                )
        return results


class RoomDowntimeSerializer(BaseModelSerializer):
    room_id = serializers.UUIDField(source="room.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = RoomDowntime
        fields = [
            "id",
            "room_id",
            "date",
            "start_time",
            "end_time",
            "reason",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        day_value = data.get("date") or getattr(self.instance, "date", None)
        start_time = data.get("start_time") or getattr(
            self.instance, "start_time", None
        )
        end_time = data.get("end_time") or getattr(self.instance, "end_time", None)
        errors = {}
        if not day_value:
            errors["date"] = ["Required."]
        if not start_time:
            errors["start_time"] = ["Required."]
        if not end_time:
            errors["end_time"] = ["Required."]
        validate_same_day_time_window(start_time, end_time, errors)
        if errors:
            raise serializers.ValidationError(errors)
        is_active = data.get(
            "is_active", getattr(self.instance, "is_active", True)
        )
        room = data.get("room") or getattr(self.instance, "room", None)
        if room is None:
            room = self.context.get("room")
        if is_active and room and day_value and start_time and end_time:
            exclude_id = self.instance.pk if self.instance is not None else None
            assert_room_downtime_no_overlap(
                room, day_value, start_time, end_time, exclude_id=exclude_id
            )
        return data


class EquipmentAvailabilityBlockSerializer(BaseModelSerializer):
    equipment_id = serializers.UUIDField(source="equipment.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = EquipmentAvailabilityBlock
        fields = [
            "id",
            "equipment_id",
            "is_recurring",
            "date",
            "start_time",
            "end_time",
            "day_of_week",
            "recurring_start_time",
            "recurring_end_time",
            "effective_from",
            "reason",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        reject_effective_until(self.initial_data)
        merged = merge_resource_block_validation_data(data, self.instance)
        merged["effective_until"] = None
        errors = {}
        if merged["is_recurring"]:
            validate_recurring_block_fields(merged, errors)
        else:
            validate_resource_one_off_day_fields(merged, errors)
        if errors:
            raise serializers.ValidationError(errors)
        if self.instance is not None and merged["is_active"]:
            assert_equipment_block_no_overlap(
                self.instance.equipment,
                merged["is_recurring"],
                merged["date"],
                merged["start_time"],
                merged["end_time"],
                merged["day_of_week"],
                merged["recurring_start_time"],
                merged["recurring_end_time"],
                merged["effective_from"],
                None,
                exclude_id=self.instance.pk,
            )
        return data

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        return clear_effective_until(instance)


class EquipmentAvailabilityBlockCreateSerializer(BaseSerializer):
    is_recurring = serializers.BooleanField(default=False)
    date = serializers.DateField(required=False, allow_null=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    days_of_week = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        allow_empty=False,
        required=False,
    )
    recurring_start_time = serializers.TimeField(required=False, allow_null=True)
    recurring_end_time = serializers.TimeField(required=False, allow_null=True)
    effective_from = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, data):
        reject_effective_until(self.initial_data)
        is_recurring = data.get("is_recurring", False)
        errors = {}
        if is_recurring:
            validate_recurring_block_create_fields(data, errors)
        else:
            if data.get("days_of_week"):
                errors["days_of_week"] = ["Not allowed for one-off blocks."]
            validate_resource_one_off_day_fields(data, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        equipment = validated_data["equipment"]
        created_by = validated_data.get("created_by")
        is_recurring = validated_data.get("is_recurring", False)
        reason = validated_data.get("reason", "")
        is_active = validated_data.get("is_active", True)
        results = []
        with transaction.atomic():
            if is_recurring:
                for day_of_week in validated_data["days_of_week"]:
                    if is_active:
                        assert_equipment_block_no_overlap(
                            equipment,
                            True,
                            None,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            None,
                        )
                    results.append(
                        create_equipment_availability_block(
                            equipment,
                            created_by,
                            True,
                            None,
                            None,
                            None,
                            day_of_week,
                            validated_data.get("recurring_start_time"),
                            validated_data.get("recurring_end_time"),
                            validated_data.get("effective_from"),
                            reason,
                            is_active,
                        )
                    )
            else:
                if is_active:
                    assert_equipment_block_no_overlap(
                        equipment,
                        False,
                        validated_data.get("date"),
                        validated_data.get("start_time"),
                        validated_data.get("end_time"),
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                results.append(
                    create_equipment_availability_block(
                        equipment,
                        created_by,
                        False,
                        validated_data.get("date"),
                        validated_data.get("start_time"),
                        validated_data.get("end_time"),
                        None,
                        None,
                        None,
                        None,
                        reason,
                        is_active,
                    )
                )
        return results


class EquipmentDowntimeSerializer(BaseModelSerializer):
    equipment_id = serializers.UUIDField(source="equipment.pk", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = EquipmentDowntime
        fields = [
            "id",
            "equipment_id",
            "date",
            "start_time",
            "end_time",
            "reason",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        day_value = data.get("date") or getattr(self.instance, "date", None)
        start_time = data.get("start_time") or getattr(
            self.instance, "start_time", None
        )
        end_time = data.get("end_time") or getattr(self.instance, "end_time", None)
        errors = {}
        if not day_value:
            errors["date"] = ["Required."]
        if not start_time:
            errors["start_time"] = ["Required."]
        if not end_time:
            errors["end_time"] = ["Required."]
        validate_same_day_time_window(start_time, end_time, errors)
        if errors:
            raise serializers.ValidationError(errors)
        is_active = data.get(
            "is_active", getattr(self.instance, "is_active", True)
        )
        equipment = data.get("equipment") or getattr(self.instance, "equipment", None)
        if equipment is None:
            equipment = self.context.get("equipment")
        if is_active and equipment and day_value and start_time and end_time:
            exclude_id = self.instance.pk if self.instance is not None else None
            assert_equipment_downtime_no_overlap(
                equipment, day_value, start_time, end_time, exclude_id=exclude_id
            )
        return data


def deactivate_unlisted_roster_days(center, associate, listed_day_values):
    AssociateRosterEntry.objects.filter(
        center=center,
        associate=associate,
        is_active=True,
    ).exclude(day_of_week__in=listed_day_values).update(
        is_active=False,
        updated_at=timezone.now(),
    )


def upsert_associate_roster_entry(
    center, associate, day_of_week, start_time, end_time, created_by
):
    existing_rows = list(
        AssociateRosterEntry.objects.filter(
            center=center, associate=associate, day_of_week=day_of_week
        ).order_by("-created_at")
    )
    if not existing_rows:
        return AssociateRosterEntry.objects.create(
            center=center,
            associate=associate,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            created_by=created_by,
            is_active=True,
        )
    matching = None
    for row in existing_rows:
        if row.start_time == start_time and row.end_time == end_time:
            matching = row
            break
    primary = matching or existing_rows[0]
    for extra in existing_rows:
        if extra.pk == primary.pk:
            continue
        if extra.is_active:
            extra.is_active = False
            extra.save(update_fields=["is_active", "updated_at"])
    primary.start_time = start_time
    primary.end_time = end_time
    primary.is_active = True
    primary.save(
        update_fields=["start_time", "end_time", "is_active", "updated_at"]
    )
    return primary


class AssociateRosterEntryInputSerializer(BaseSerializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate(self, data):
        if data["start_time"] >= data["end_time"]:
            raise serializers.ValidationError(
                {"end_time": ["Must be after start_time."]}
            )
        return data


class AssociateRosterBulkUpsertSerializer(BaseSerializer):
    entries = AssociateRosterEntryInputSerializer(many=True, allow_empty=False)

    def validate_entries(self, entries):
        days = [entry["day_of_week"] for entry in entries]
        if len(days) != len(set(days)):
            raise serializers.ValidationError(
                "Duplicate day_of_week values are not allowed in one request."
            )
        return entries

    def create(self, validated_data):
        center = validated_data["center"]
        associate = validated_data["associate"]
        created_by = validated_data.get("created_by")
        replace_unlisted = validated_data.pop("replace_unlisted", False)
        assert_roster_within_operating_hours(center, validated_data["entries"])
        results = []
        listed_day_values = []
        with transaction.atomic():
            for entry in validated_data["entries"]:
                day_of_week = str(entry["day_of_week"])
                listed_day_values.append(day_of_week)
                results.append(
                    upsert_associate_roster_entry(
                        center,
                        associate,
                        day_of_week,
                        entry["start_time"],
                        entry["end_time"],
                        created_by,
                    )
                )
            if replace_unlisted:
                deactivate_unlisted_roster_days(
                    center, associate, listed_day_values
                )
        return results


class CenterOperatingHourSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(source="center.pk", read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = CenterOperatingHour
        fields = [
            "id",
            "center_id",
            "day_of_week",
            "is_open",
            "open_time",
            "close_time",
            "is_active",
            "created_at",
            "updated_at",
        ]


def upsert_center_operating_hour(
    center, day_of_week, is_open, open_time, close_time
):
    existing_rows = list(
        CenterOperatingHour.objects.filter(center=center, day_of_week=day_of_week)
        .order_by("-created_at")
    )
    if not existing_rows:
        return CenterOperatingHour.objects.create(
            center=center,
            day_of_week=day_of_week,
            is_open=is_open,
            open_time=open_time,
            close_time=close_time,
            is_active=True,
        )
    primary = existing_rows[0]
    for extra in existing_rows[1:]:
        extra.is_active = False
        if not extra.is_open:
            extra.is_open = True
            extra.open_time = None
            extra.close_time = None
            extra.save(
                update_fields=[
                    "is_active",
                    "is_open",
                    "open_time",
                    "close_time",
                    "updated_at",
                ]
            )
        else:
            extra.save(update_fields=["is_active", "updated_at"])
    primary.is_open = is_open
    primary.open_time = open_time
    primary.close_time = close_time
    primary.is_active = True
    primary.save(
        update_fields=[
            "is_open",
            "open_time",
            "close_time",
            "is_active",
            "updated_at",
        ]
    )
    return primary


class CenterOperatingHoursBulkUpsertSerializer(BaseSerializer):
    open_time = serializers.TimeField(required=False, allow_null=True)
    close_time = serializers.TimeField(required=False, allow_null=True)
    days = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        required=False,
        default=list,
    )
    closed_days = serializers.ListField(
        child=serializers.ChoiceField(choices=AppointmentDays.choices),
        required=False,
        default=list,
    )

    def validate(self, data):
        errors = {}
        days = data.get("days") or []
        closed_days = data.get("closed_days") or []
        open_time = data.get("open_time")
        close_time = data.get("close_time")
        if not days and not closed_days:
            errors["days"] = ["Provide at least one open day or closed day."]
        overlapping_days = set(days) & set(closed_days)
        if overlapping_days:
            errors["closed_days"] = [
                f"Days cannot appear in both days and closed_days: {sorted(overlapping_days)}."
            ]
        if days:
            if open_time is None:
                errors["open_time"] = ["Required when days is provided."]
            if close_time is None:
                errors["close_time"] = ["Required when days is provided."]
            if open_time is not None and close_time is not None and open_time >= close_time:
                errors["close_time"] = ["Must be after open_time."]
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        center = validated_data["center"]
        open_time = validated_data.get("open_time")
        close_time = validated_data.get("close_time")
        days = validated_data.get("days") or []
        closed_days = validated_data.get("closed_days") or []
        assert_operating_hours_cover_roster(
            center, days, closed_days, open_time, close_time
        )
        results = []
        with transaction.atomic():
            for day_of_week in days:
                results.append(
                    upsert_center_operating_hour(
                        center,
                        day_of_week,
                        is_open=True,
                        open_time=open_time,
                        close_time=close_time,
                    )
                )
            for day_of_week in closed_days:
                results.append(
                    upsert_center_operating_hour(
                        center,
                        day_of_week,
                        is_open=False,
                        open_time=None,
                        close_time=None,
                    )
                )
        return results


class CenterClosureSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(source="center.pk", read_only=True)
    is_active = serializers.BooleanField(required=False, default=True)
    type = serializers.ChoiceField(choices=CenterClosureType.choices)
    reason = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)

    class Meta:
        model = CenterClosure
        fields = [
            "id",
            "center_id",
            "date",
            "type",
            "reason",
            "is_active",
            "created_at",
            "updated_at",
        ]


class CenterClosureWriteSerializer(CenterClosureSerializer):
    class Meta(CenterClosureSerializer.Meta):
        read_only_fields = [
            "id",
            "center_id",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        if self.instance is not None:
            return data
        center = self.context.get("center")
        closure_date = data.get("date")
        if center is None or closure_date is None:
            return data
        existing = CenterClosure.objects.filter(
            center=center, date=closure_date
        ).first()
        if existing is None:
            return data
        if existing.is_active:
            raise serializers.ValidationError(
                {"date": ["An active closure already exists for this date."]}
            )
        self.context["existing_inactive_closure"] = existing
        return data

    def create(self, validated_data):
        existing = self.context.get("existing_inactive_closure")
        if existing is not None:
            existing.is_active = True
            existing.type = validated_data["type"]
            existing.reason = validated_data["reason"]
            existing.save(
                update_fields=["is_active", "type", "reason", "updated_at"]
            )
            return existing
        return super().create(validated_data)
