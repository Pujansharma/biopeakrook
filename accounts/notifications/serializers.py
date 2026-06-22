from core.utils.serializers import BaseModelSerializer
from .models import FirebaseRegistrationToken
from .utils.db import save_firebase_registration_token


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
