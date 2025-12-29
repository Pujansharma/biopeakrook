class UserType:
    ADMIN = "admin"
    SUPERUSER = "superuser"
    UNKNOWN = "unknown"
    ASSOCIATE = "associate"
    CUSTOMER = "customer"


USER_TYPE_CHOICES = (
    (UserType.ADMIN, "Admin"),
    (UserType.SUPERUSER, 'Superuser'),
    (UserType.UNKNOWN, "Unknown"),

    (UserType.ASSOCIATE, "Associate"),
    (UserType.CUSTOMER, 'Customer'),
)
