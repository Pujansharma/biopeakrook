from accounts.notifications.models import FirebaseRegistrationToken, UserNotification
from accounts.notifications.utils.sdk import send_firebase_notification


def save_firebase_registration_token(
        user, ip_address, user_agent, token, project_id
):
    registration_token, _ = FirebaseRegistrationToken.objects.update_or_create(
        user=user,
        project_id=project_id,
        user_agent=user_agent,
        defaults={
            "ip_address": ip_address,
            "token": token,
        },
    )
    return registration_token


def send_user_notification(
        user,
        title,
        body,
        notification_type,
        project_id,
        token,
        image=None,
        data=None,
):
    if not token:
        return None

    if not data:
        return None

    notification = UserNotification.objects.create(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        project_id=project_id,
        data=data,
    )

    payload = {
        **data,
        "notification_id": str(notification.pk),
    }

    firebase_message_id = send_firebase_notification(
        project_id, token, title, body, image, payload
    )

    notification.firebase_message_id = firebase_message_id
    notification.save(update_fields=["firebase_message_id"])

    return notification
