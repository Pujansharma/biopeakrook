class UserType:
    ADMIN = "admin"
    SUPERUSER = "superuser"
    UNKNOWN = "unknown"


USER_TYPE_CHOICES = (
    (UserType.ADMIN, "Admin"),
    (UserType.SUPERUSER, 'Superuser'),
    (UserType.UNKNOWN, "Unknown"),
)
