from rest_framework.permissions import IsAuthenticated

from accounts.notifications.serializers import FirebaseRegistrationTokenSerializer
from core.utils.views.main import BaseCreateAPIView


class FirebaseRegistrationView(BaseCreateAPIView):
    serializer_class = FirebaseRegistrationTokenSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user
        )
