from accounts.notifications.models import FirebaseRegistrationToken


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
