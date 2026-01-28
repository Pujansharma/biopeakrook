class UserType:
    UNKNOWN = "unknown"
    SUPERUSER = "superuser"
    ADMIN = "admin"
    ASSOCIATE = "associate"
    CUSTOMER = "customer"


USER_TYPE_CHOICES = (
    (UserType.UNKNOWN, "Unknown"),
    (UserType.SUPERUSER, 'Superuser'),
    (UserType.ADMIN, "Admin"),

    (UserType.ASSOCIATE, "Associate"),
    (UserType.CUSTOMER, 'Customer'),
)


class UserRoleType:
    OTHER = 'other'
    CENTER_ADMIN = 'center_admin'
    SPECIALIST = "specialist"

    CHOICES = (
        (OTHER, 'Other'),
        (CENTER_ADMIN, "Center Admin"),
        (SPECIALIST, "Specialist"),
    )
