import json
from typing import Any

import firebase_admin
from django.conf import settings
from firebase_admin import credentials
from firebase_admin import messaging

from accounts.notifications.utils.constants import NotificationProjectID

ADMIN_CERT = settings.ADMIN_CERT
APP_CERT = settings.APP_CERT


class FirebaseApp:
    initialized_apps = []
    FIREBASE_CRED_DIR = settings.BASE_DIR / ".firebase"

    PROJECT_KEY_MAP = {
        NotificationProjectID.APP: APP_CERT,
        NotificationProjectID.ADMIN: ADMIN_CERT,
    }

    def get_certificate_data(self, project_id):
        cert: str | None = self.PROJECT_KEY_MAP.get(project_id, APP_CERT)
        if cert is None:
            return None

        try:
            return json.loads(cert)
        except json.JSONDecodeError:
            return None

    def initialize_app(self, project_id=NotificationProjectID.APP):
        data = self.get_certificate_data(project_id)
        cred = credentials.Certificate(data)
        app = firebase_admin.initialize_app(cred, name=project_id)
        self.initialized_apps.append(project_id)
        return app

    def get_app(self, project_id):
        if project_id in self.initialized_apps:
            return firebase_admin.get_app(project_id)
        return self.initialize_app(project_id)


def get_app_for_project_id(project_id):
    return FirebaseApp().get_app(project_id)


def subscribe_firebase_topic(project_id, token, topic="default"):
    app = get_app_for_project_id(project_id)
    response = messaging.subscribe_to_topic(token, topic, app=app)
    return response


def send_firebase_notification(
        project_id: str, token: str, title: str, body: str, image=None, data=None
):
    app = get_app_for_project_id(project_id)
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
            image=image,
        ),
        data=data,
        token=token,
    )
    return messaging.send(message, app=app)


def _build_firebase_data(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    firebase_payload = {}
    for key, value in payload.items():
        if not value:
            continue
        firebase_payload[key] = value

        if isinstance(value, (dict, list)):
            firebase_payload[key] = json.dumps(value)
    return firebase_payload


def send_multicast_firebase_notification(
        project_id: str,
        tokens: list[str],
        title: str,
        body: str,
        image: str | None = None,
        data: dict[str, Any] | None = None,
):
    if not tokens:
        return None
    app = get_app_for_project_id(project_id)

    multicast_message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body, image=image),
        data=_build_firebase_data(data),
        tokens=tokens,
    )
    return messaging.send_each_for_multicast(multicast_message, app=app)


def send_firebase_data(project_id, token, data):
    app = get_app_for_project_id(project_id)
    message = messaging.Message(data=data, token=token)
    return messaging.send(message, app=app)


def send_dry_run_message(token, project_id):
    app = get_app_for_project_id(project_id)
    message = messaging.Message(token=token)
    return messaging.send(message, dry_run=True, app=app)
