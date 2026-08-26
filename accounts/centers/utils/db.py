import pandas as pd
from django.db.models import Count, F, Value, Case, When
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Coalesce

from accounts.associates.models import AssociateCenterAssignment
from accounts.centers.models import Center, CenterOperatingHour
from sequences.utils import get_next_sequence


def generate_center_code():
    name = "CT"
    sequence = get_next_sequence(name=name, fill_length=4)
    return f"{name}-{sequence}"


def build_center_resource_code(prefix, sequence_name, center_id):
    center_code = (
        Center.objects.filter(pk=center_id).values_list("code", flat=True).first()
    )
    sequence = get_next_sequence(name=sequence_name, fill_length=4)
    return f"{prefix}-{center_code}-{sequence}"


def generate_room_code(center_id):
    return build_center_resource_code("RM", f"rooms_{center_id}", center_id)


def generate_equipment_code(center_id):
    return build_center_resource_code("EQ", f"equipments_{center_id}", center_id)


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


def refresh_staff_counts(center_ids: list) -> None:
    staff_subquery = Coalesce(
        Subquery(
            AssociateCenterAssignment.objects.filter(center_id=OuterRef("pk"))
            .order_by()
            .values("center_id")
            .annotate(count=Count("id"))
            .values("count")
        ),
        Value(0),
    )
    inactive_staff_subquery = Coalesce(
        Subquery(
            AssociateCenterAssignment.objects.filter(
                center_id=OuterRef("pk"),
                associate__user__is_active=False,
            )
            .order_by()
            .values("center_id")
            .annotate(count=Count("id"))
            .values("count")
        ),
        Value(0),
    )
    Center.objects.filter(pk__in=center_ids).update(
        staff_count=staff_subquery,
        inactive_staff_count=inactive_staff_subquery,
    )


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
