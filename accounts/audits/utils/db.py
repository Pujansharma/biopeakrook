from accounts.audits.models import AuditLog
from accounts.utils.db import get_user_account_type


def add_audit_log(
    user, center_id, action, entity_type, entity_id=None, description="", metadata=None
):
    """
    Base function to create an audit log entry.
    Reads user, user_type, and center_id from the request.
    """

    user_type = get_user_account_type(user)

    return AuditLog.objects.create(
        user=user,
        user_type=user_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        center_id=center_id,
        description=description,
        metadata=metadata or {},
    )


def add_audit_log_for_center(user, center_id, action, description="", metadata=None):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.CENTER,
        entity_id=center_id,
        description=description,
        metadata=metadata,
    )


def add_audit_log_for_associate(
    user, center_id, action, associate_id, description="", metadata=None
):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.ASSOCIATE,
        entity_id=associate_id,
        description=description,
        metadata=metadata,
    )


def add_audit_log_for_associate_role(
    user, center_id, action, role_id, description="", metadata=None
):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.ASSOCIATE_ROLE,
        entity_id=role_id,
        description=description,
        metadata=metadata,
    )


def add_audit_log_for_customer(
    user, center_id, action, customer_id, description="", metadata=None
):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.CUSTOMER,
        entity_id=customer_id,
        description=description,
        metadata=metadata,
    )


def add_audit_log_for_appointment(
    user, center_id, action, appointment_id, description="", metadata=None
):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.APPOINTMENT,
        entity_id=appointment_id,
        description=description,
        metadata=metadata,
    )


def add_audit_log_for_package(
    user, center_id, action, package_id, description="", metadata=None
):
    return add_audit_log(
        user,
        center_id,
        action=action,
        entity_type=EntityType.PACKAGE,
        entity_id=package_id,
        description=description,
        metadata=metadata,
    )
