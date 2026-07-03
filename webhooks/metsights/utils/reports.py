from accounts.notifications.models import FirebaseRegistrationToken
from accounts.notifications.utils.constants import (
    NotificationType,
    NotificationProjectID,
)
from accounts.notifications.utils.db import send_user_notification
from accounts.users.models import User


def perform_file_upload_action(data: dict) -> None:
    profile = data.get("profile", {}) or {}
    phone = profile.get("phone", None)
    if not phone:
        return None

    user = User.objects.exclude(phone__isnull=True).filter(phone=phone).first()

    if not user:
        return None
    project_id = NotificationProjectID.APP
    firebase_tokens = FirebaseRegistrationToken.objects.filter(
        user=user, token__isnull=False, project_id=project_id
    ).values_list("token", flat=True)

    if not firebase_tokens:
        return None

    attachment = data.get("attachment", {}) or {}
    attachment_metadata = data.get("metadata", {}) or {}

    if attachment_metadata.get('category_type') in [
        'consultation_notes',
        'unknown',
    ]:
        return None

    send_user_notification(
        user,
        title="Health reports updated",
        body="Your health reports have been updated with the latest details and are now available for review.",
        notification_type=NotificationType.METSIGHTS_FILE_UPLOAD,
        project_id=project_id,
        tokens=list(firebase_tokens),
        image=None,
        data=data,
    )

    return None
