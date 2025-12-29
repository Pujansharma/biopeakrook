from appointments.utils.db import get_schedules_for_associate


def generate_slots(specialist, from_datetime, to_datetime):
    schedules_data = get_schedules_for_associate(specialist)



