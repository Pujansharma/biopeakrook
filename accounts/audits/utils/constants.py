class EntityType:
    CENTER = "center"
    ASSOCIATE = "associate"
    ASSOCIATE_ROLE = "associate_role"
    CUSTOMER = "customer"
    APPOINTMENT = "appointment"
    PACKAGE = "package"


class AuditAction:
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    CHOICES = (
        (CREATE, "Create"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
    )
