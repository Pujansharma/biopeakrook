from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated

from accounts.users.serializers import UserProfileSerializer
from core.utils.views import BaseRetrieveUpdateAPIView

User = get_user_model()


class UserProfileView(BaseRetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(pk=self.request.user.pk)

    def get_object(self):
        return self.get_queryset().get()
