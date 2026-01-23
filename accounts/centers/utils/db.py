import pandas as pd

from accounts.centers.models import CenterOperatingHour
from sequences.utils import get_next_sequence


def generate_center_code():
    name = 'CT'
    sequence = get_next_sequence(name=name, fill_length=4)
    return f"{name}-{sequence}"


def check_overlap(
        center, day_of_week, start_time, end_time, exclude_id=None
):
    # Fetch existing hours
    existing = CenterOperatingHour.objects.filter(
        center=center,
        day_of_week=day_of_week,
        is_open=True
    )

    if exclude_id:
        existing = existing.exclude(pk=exclude_id)

    if not existing.exists():
        return False, []

    # Convert to DataFrame
    df = pd.DataFrame(list(existing.values('id', 'open_time', 'close_time')))

    # Pandas overlap check using IntervalIndex or boolean masking
    df['overlaps'] = (start_time < df['close_time']) & (end_time > df['open_time'])

    overlapping = df[df['overlaps']]

    if overlapping.empty:
        return False, []

    overlaps_list = overlapping[['open_time', 'close_time']].to_dict('records')
    return True, overlaps_list
