from accounts.notifications.models import FirebaseRegistrationToken, UserNotification
from core.utils.helper import fetch_file_from_url
from accounts.notifications.utils.sdk import send_multicast_firebase_notification


def save_firebase_registration_token(user, ip_address, user_agent, token, project_id):
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
        tokens,
        project_id,
        image=None,
        data=None,
):
    if not tokens:
        return None

    if not data:
        return None
    _image = None
    if image:
        _image = fetch_file_from_url(_image)

    notification = UserNotification.objects.create(
        user=user,
        title=title,
        body=body,
        image=_image,
        notification_type=notification_type,
        project_id=project_id,
        data=data,
    )

    payload = {
        **data,
        "notification_id": str(notification.pk),
        "notification_type": notification_type,
    }

    firebase_message_id = send_multicast_firebase_notification(
        project_id,
        tokens,
        title=title,
        body=body,
        image=image,
        data=payload,
    )

    notification.firebase_message_id = firebase_message_id
    notification.save(update_fields=["firebase_message_id"])

    return notification
