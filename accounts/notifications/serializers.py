from rest_framework import serializers

from accounts.notifications.models import FirebaseRegistrationToken, UserNotification
from accounts.notifications.utils.db import save_firebase_registration_token
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class FirebaseRegistrationTokenSerializer(BaseModelSerializer):
    class Meta:
        model = FirebaseRegistrationToken
        fields = ["token", "project_id"]

    def create(self, validated_data):
        user = validated_data.get("user")
        ip_address = validated_data.get("ip_address")
        user_agent = validated_data.get("user_agent")
        token = validated_data.get("token")
        project_id = validated_data.get("project_id")
        return save_firebase_registration_token(
            user, ip_address, user_agent, token, project_id
        )


class FirebaseRegistrationTokenDeregisterSerializer(BaseSerializer):
    token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        FirebaseRegistrationToken.objects.filter(
            user=user,
            token=attrs["token"],
        ).delete()
        return attrs


class UserNotificationSerializer(BaseModelSerializer):
    notification_type_code = serializers.CharField(
        source="notification_type", read_only=True
    )

    class Meta:
        model = UserNotification
        fields = [
            "id",
            "title",
            "body",
            "notification_type",
            "notification_type_code",
            "created_at",
            "seen_at",
            "data",
        ]
