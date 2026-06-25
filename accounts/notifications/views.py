from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

from accounts.notifications.models import UserNotification
from accounts.notifications.serializers import (
    FirebaseRegistrationTokenDeregisterSerializer,
    FirebaseRegistrationTokenSerializer,
    UserNotificationSerializer,
)
from core.utils.exceptions import get_object_or_404
from core.utils.helper import get_request_ip_address, get_request_user_agent
from core.utils.views.main import (
    BaseCreateAPIView,
    BaseListAPIView,
    BaseRetrieveAPIView,
)


class FirebaseRegistrationView(BaseCreateAPIView):
    serializer_class = FirebaseRegistrationTokenSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        ip_address = get_request_ip_address(self.request)
        user_agent = get_request_user_agent(self.request)
        serializer.save(
            user=self.request.user,
            ip_address=ip_address,
            user_agent=user_agent,
        )


class FirebaseRegistrationDeregisterView(BaseCreateAPIView):
    serializer_class = FirebaseRegistrationTokenDeregisterSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("Firebase token deregistered successfully")


class UserNotificationListView(BaseListAPIView):
    serializer_class = UserNotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filter_kwargs = {}
        is_read_query = self.request.query_params.get("read", None)

        if is_read_query and is_read_query in ["0", "1"]:
            filter_kwargs["seen_at__isnull"] = not bool(int(is_read_query))

        return UserNotification.objects.filter(
            user=self.request.user,
            **filter_kwargs,
        )


class UserNotificationDetailView(BaseRetrieveAPIView):
    serializer_class = UserNotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserNotification.objects.filter(user=self.request.user)

    def get_object(self):
        queryset = self.get_queryset()
        notification = get_object_or_404(
            queryset, "Notification not found", pk=self.kwargs["pk"]
        )
        if not notification.seen_at:
            notification.seen_at = timezone.localtime()
            notification.save(update_fields=["seen_at"])
        return notification
