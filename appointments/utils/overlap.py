from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, models
from rest_framework import serializers

from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    CareTeamAvailabilityBlock,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.utils.constants import LeaveScope

UTC = ZoneInfo("UTC")
OVERLAP_ERROR = "Overlaps an existing unavailability window."
CARE_TEAM_ONE_OFF_OVERLAP_CONSTRAINT = "care_team_block_one_off_no_overlap"


def get_availability_timezone_name():
    return settings.TIME_ZONE


def datetimes_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and end_a > start_b


def times_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and end_a > start_b


def date_ranges_overlap(start_a, end_a, start_b, end_b):
    range_end_a = end_a or date.max
    range_end_b = end_b or date.max
    return start_a <= range_end_b and range_end_a >= start_b


def raise_overlap():
    raise serializers.ValidationError({"non_field_errors": [OVERLAP_ERROR]})


def raise_if_care_team_one_off_overlap_integrity(error):
    if CARE_TEAM_ONE_OFF_OVERLAP_CONSTRAINT in str(error):
        raise_overlap()
    raise error


def local_day_window(day_value, start_time, end_time, timezone_name):
    zone = ZoneInfo(timezone_name)
    start_local = datetime.combine(day_value, start_time, tzinfo=zone)
    end_local = datetime.combine(day_value, end_time, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


SAME_DAY_TIME_ERROR = "Must be after start_time on the same day."


def day_window_utc(day_value, start_time, end_time, timezone_name=None):
    if timezone_name is None:
        timezone_name = get_availability_timezone_name()
    return local_day_window(day_value, start_time, end_time, timezone_name)


def validate_same_day_time_window(start_time, end_time, errors):
    if start_time is None or end_time is None:
        return
    if start_time >= end_time:
        errors["end_time"] = [SAME_DAY_TIME_ERROR]


def one_off_day_window(day_value, start_time, end_time, timezone_name=None):
    if day_value is None or start_time is None or end_time is None:
        return None
    return day_window_utc(day_value, start_time, end_time, timezone_name)


def iter_local_dates(start_datetime, end_datetime, timezone_name):
    zone = ZoneInfo(timezone_name)
    start_local = start_datetime.astimezone(zone)
    end_local = end_datetime.astimezone(zone)
    current = start_local.date()
    last = end_local.date()
    while current <= last:
        yield current
        current += timedelta(days=1)


def one_off_overlaps_recurring_block(
    start_datetime,
    end_datetime,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    timezone_name,
):
    if not all(
        [
            day_of_week,
            recurring_start_time,
            recurring_end_time,
            effective_from,
            start_datetime,
            end_datetime,
        ]
    ):
        return False
    for day_value in iter_local_dates(start_datetime, end_datetime, timezone_name):
        if str(day_value.weekday()) != str(day_of_week):
            continue
        if day_value < effective_from:
            continue
        if effective_until and day_value > effective_until:
            continue
        window_start, window_end = local_day_window(
            day_value, recurring_start_time, recurring_end_time, timezone_name
        )
        if datetimes_overlap(start_datetime, end_datetime, window_start, window_end):
            return True
    return False


def recurring_blocks_overlap(
    day_a,
    start_time_a,
    end_time_a,
    effective_from_a,
    effective_until_a,
    day_b,
    start_time_b,
    end_time_b,
    effective_from_b,
    effective_until_b,
):
    if str(day_a) != str(day_b):
        return False
    if not times_overlap(start_time_a, end_time_a, start_time_b, end_time_b):
        return False
    return date_ranges_overlap(
        effective_from_a, effective_until_a, effective_from_b, effective_until_b
    )


def exclude_pk(queryset, exclude_id):
    if exclude_id is None:
        return queryset
    return queryset.exclude(pk=exclude_id)


def assert_associate_block_no_overlap(
    center,
    associate,
    is_recurring,
    start_datetime,
    end_datetime,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    exclude_id=None,
):
    timezone_name = get_availability_timezone_name()
    blocks = exclude_pk(
        AssociateAvailabilityBlock.objects.filter(
            center=center, associate=associate, is_active=True
        ),
        exclude_id,
    )
    for block in blocks:
        if is_recurring and block.is_recurring:
            if recurring_blocks_overlap(
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
            ):
                raise_overlap()
        elif is_recurring and not block.is_recurring:
            if one_off_overlaps_recurring_block(
                block.start_datetime,
                block.end_datetime,
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif not is_recurring and block.is_recurring:
            if one_off_overlaps_recurring_block(
                start_datetime,
                end_datetime,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif datetimes_overlap(
            start_datetime, end_datetime, block.start_datetime, block.end_datetime
        ):
            raise_overlap()

    leaves = AssociateLeave.objects.filter(associate=associate, is_active=True).filter(
        models.Q(scope=LeaveScope.ALL_CENTERS) | models.Q(center=center)
    )
    if not is_recurring:
        for leave in leaves:
            if datetimes_overlap(
                start_datetime, end_datetime, leave.start_datetime, leave.end_datetime
            ):
                raise_overlap()
    else:
        for leave in leaves:
            if one_off_overlaps_recurring_block(
                leave.start_datetime,
                leave.end_datetime,
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()


def assert_care_team_block_no_overlap(
    center,
    care_team,
    is_recurring,
    start_datetime,
    end_datetime,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    exclude_id=None,
):
    timezone_name = get_availability_timezone_name()
    blocks = exclude_pk(
        CareTeamAvailabilityBlock.objects.filter(
            center=center, care_team=care_team, is_active=True
        ),
        exclude_id,
    )
    for block in blocks:
        if is_recurring and block.is_recurring:
            if recurring_blocks_overlap(
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
            ):
                raise_overlap()
        elif is_recurring and not block.is_recurring:
            if one_off_overlaps_recurring_block(
                block.start_datetime,
                block.end_datetime,
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif not is_recurring and block.is_recurring:
            if one_off_overlaps_recurring_block(
                start_datetime,
                end_datetime,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif datetimes_overlap(
            start_datetime, end_datetime, block.start_datetime, block.end_datetime
        ):
            raise_overlap()


def assert_associate_leave_no_overlap(
    associate, scope, center, start_datetime, end_datetime, exclude_id=None
):
    leaves = AssociateLeave.objects.filter(associate=associate, is_active=True)
    leaves = exclude_pk(leaves, exclude_id)
    for leave in leaves:
        same_scope = False
        if leave.scope == LeaveScope.ALL_CENTERS or scope == LeaveScope.ALL_CENTERS:
            same_scope = True
        elif leave.center_id == getattr(center, "pk", center):
            same_scope = True
        if not same_scope:
            continue
        if datetimes_overlap(
            start_datetime, end_datetime, leave.start_datetime, leave.end_datetime
        ):
            raise_overlap()


def assert_room_block_no_overlap(
    room,
    is_recurring,
    day_value,
    start_time,
    end_time,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    exclude_id=None,
):
    timezone_name = get_availability_timezone_name()
    one_off_window = one_off_day_window(
        day_value, start_time, end_time, timezone_name
    )
    blocks = exclude_pk(
        RoomAvailabilityBlock.objects.filter(room=room, is_active=True),
        exclude_id,
    )
    for block in blocks:
        if is_recurring and block.is_recurring:
            if recurring_blocks_overlap(
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
            ):
                raise_overlap()
        elif is_recurring and not block.is_recurring:
            existing_window = one_off_day_window(
                block.date, block.start_time, block.end_time, timezone_name
            )
            if existing_window and one_off_overlaps_recurring_block(
                existing_window[0],
                existing_window[1],
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif not is_recurring and block.is_recurring:
            if one_off_window and one_off_overlaps_recurring_block(
                one_off_window[0],
                one_off_window[1],
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif (
            one_off_window
            and block.date == day_value
            and times_overlap(start_time, end_time, block.start_time, block.end_time)
        ):
            raise_overlap()

    downtimes = RoomDowntime.objects.filter(room=room, is_active=True)
    for downtime in downtimes:
        downtime_window = one_off_day_window(
            downtime.date, downtime.start_time, downtime.end_time, timezone_name
        )
        if not downtime_window:
            continue
        if is_recurring:
            if one_off_overlaps_recurring_block(
                downtime_window[0],
                downtime_window[1],
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif (
            one_off_window
            and downtime.date == day_value
            and times_overlap(
                start_time, end_time, downtime.start_time, downtime.end_time
            )
        ):
            raise_overlap()


def assert_room_downtime_no_overlap(
    room, day_value, start_time, end_time, exclude_id=None
):
    downtimes = exclude_pk(
        RoomDowntime.objects.filter(room=room, is_active=True),
        exclude_id,
    )
    for downtime in downtimes:
        if downtime.date == day_value and times_overlap(
            start_time, end_time, downtime.start_time, downtime.end_time
        ):
            raise_overlap()


def assert_equipment_block_no_overlap(
    equipment,
    is_recurring,
    day_value,
    start_time,
    end_time,
    day_of_week,
    recurring_start_time,
    recurring_end_time,
    effective_from,
    effective_until,
    exclude_id=None,
):
    timezone_name = get_availability_timezone_name()
    one_off_window = one_off_day_window(
        day_value, start_time, end_time, timezone_name
    )
    blocks = exclude_pk(
        EquipmentAvailabilityBlock.objects.filter(equipment=equipment, is_active=True),
        exclude_id,
    )
    for block in blocks:
        if is_recurring and block.is_recurring:
            if recurring_blocks_overlap(
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
            ):
                raise_overlap()
        elif is_recurring and not block.is_recurring:
            existing_window = one_off_day_window(
                block.date, block.start_time, block.end_time, timezone_name
            )
            if existing_window and one_off_overlaps_recurring_block(
                existing_window[0],
                existing_window[1],
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif not is_recurring and block.is_recurring:
            if one_off_window and one_off_overlaps_recurring_block(
                one_off_window[0],
                one_off_window[1],
                block.day_of_week,
                block.recurring_start_time,
                block.recurring_end_time,
                block.effective_from,
                block.effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif (
            one_off_window
            and block.date == day_value
            and times_overlap(start_time, end_time, block.start_time, block.end_time)
        ):
            raise_overlap()

    downtimes = EquipmentDowntime.objects.filter(equipment=equipment, is_active=True)
    for downtime in downtimes:
        downtime_window = one_off_day_window(
            downtime.date, downtime.start_time, downtime.end_time, timezone_name
        )
        if not downtime_window:
            continue
        if is_recurring:
            if one_off_overlaps_recurring_block(
                downtime_window[0],
                downtime_window[1],
                day_of_week,
                recurring_start_time,
                recurring_end_time,
                effective_from,
                effective_until,
                timezone_name,
            ):
                raise_overlap()
        elif (
            one_off_window
            and downtime.date == day_value
            and times_overlap(
                start_time, end_time, downtime.start_time, downtime.end_time
            )
        ):
            raise_overlap()


def assert_equipment_downtime_no_overlap(
    equipment, day_value, start_time, end_time, exclude_id=None
):
    downtimes = exclude_pk(
        EquipmentDowntime.objects.filter(equipment=equipment, is_active=True),
        exclude_id,
    )
    for downtime in downtimes:
        if downtime.date == day_value and times_overlap(
            start_time, end_time, downtime.start_time, downtime.end_time
        ):
            raise_overlap()
