import pandas as pd
from django.db.models import F, Value, Case, When

from accounts.centers.models import Center, CenterOperatingHour
from sequences.utils import get_next_sequence


def generate_center_code():
    name = "CT"
    sequence = get_next_sequence(name=name, fill_length=4)
    return f"{name}-{sequence}"


def generate_room_code(center_id):
    name = "RM"
    sequence = get_next_sequence(name=f"rooms_{center_id}", fill_length=4)
    return f"{name}-{sequence}"


def generate_equipment_code(center_id):
    name = "EQ"
    sequence = get_next_sequence(name=f"equipments_{center_id}", fill_length=4)
    return f"{name}-{sequence}"


def check_overlap(center, day_of_week, start_time, end_time, exclude_id=None):
    # Fetch existing hours
    existing = CenterOperatingHour.objects.filter(
        center=center, day_of_week=day_of_week, is_open=True
    )

    if exclude_id:
        existing = existing.exclude(pk=exclude_id)

    if not existing.exists():
        return False, []

    # Convert to DataFrame
    df = pd.DataFrame(list(existing.values("id", "open_time", "close_time")))

    # Pandas overlap check using IntervalIndex or boolean masking
    df["overlaps"] = (start_time < df["close_time"]) & (end_time > df["open_time"])

    overlapping = df[df["overlaps"]]

    if overlapping.empty:
        return False, []

    overlaps_list = overlapping[["open_time", "close_time"]].to_dict("records")
    return True, overlaps_list


def increment_staff_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(staff_count=F("staff_count") + 1)


def decrement_staff_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        staff_count=Case(
            When(staff_count__gt=0, then=F("staff_count") - 1),
            default=Value(0),
        )
    )


def increment_inactive_staff_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        inactive_staff_count=F("inactive_staff_count") + 1
    )


def decrement_inactive_staff_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        inactive_staff_count=Case(
            When(inactive_staff_count__gt=0, then=F("inactive_staff_count") - 1),
            default=Value(0),
        )
    )


def increment_customer_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(customer_count=F("customer_count") + 1)


def decrement_customer_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        customer_count=Case(
            When(customer_count__gt=0, then=F("customer_count") - 1),
            default=Value(0),
        )
    )


def increment_inactive_customer_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        inactive_customer_count=F("inactive_customer_count") + 1
    )


def decrement_inactive_customer_count(center_id) -> None:
    Center.objects.filter(pk=center_id).update(
        inactive_customer_count=Case(
            When(inactive_customer_count__gt=0, then=F("inactive_customer_count") - 1),
            default=Value(0),
        )
    )
