class AppointmentDays:
    MONDAY = '0'
    TUESDAY = '1'
    WEDNESDAY = '2'
    THURSDAY = '3'
    FRIDAY = '4'
    SATURDAY = '5'
    SUNDAY = '6'

    CHOICES = (
        (MONDAY, "Monday"),
        (TUESDAY, "Tuesday"),
        (WEDNESDAY, 'Wednesday'),
        (THURSDAY, 'Thursday'),
        (FRIDAY, 'Friday'),
        (SATURDAY, 'Saturday'),
        (SUNDAY, 'Sunday'),

    )


class ScheduleModes:
    VIRTUAL = 'virtual'
    IN_PERSON = "in_person"
    BOTH = 'both'

    CHOICES = (
        (VIRTUAL, 'Virtual Mode'),
        (IN_PERSON, 'In person mode'),
        (BOTH, 'Both')
    )


class AppointmentModes:
    CHOICES = (
        (ScheduleModes.VIRTUAL, "Virtual Mode"),
        (ScheduleModes.IN_PERSON, 'In person mode'),
    )


class AppointmentStatus:
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    NO_SHOW = 'no_show'

    CHOICES = (
        (PENDING, 'Pending'),
        (CONFIRMED, 'Confirmed'),
        (CANCELLED, 'Cancelled'),
        (COMPLETED, 'Completed'),
        (NO_SHOW, 'No Show'),
    )
