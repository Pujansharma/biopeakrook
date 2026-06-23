from accounts.notifications.models import FirebaseRegistrationToken
from accounts.notifications.utils.constants import NotificationType
from accounts.notifications.utils.db import send_user_notification


def perform_file_upload_action(data):
    profile = data.get('profile', {}) or {}
    phone = profile.get('phone', None)

    firebase_token = FirebaseRegistrationToken.objects.filter(
        user__phone=phone, token__isnull=False
    ).first()

    user = firebase_token.user
    token = firebase_token.token

    attachment = data.get('attachment', {}) or {}
    attachment_metadata = data.get('metadata', {}) or {}

    send_user_notification(
        user,
        title="Health reports updated",
        body="",
        notification_type=NotificationType.METSIGHTS_FILE_UPLOAD,
        project_id=firebase_token.project_id,
        token=token,
        image=None,
        data=data,
    )
