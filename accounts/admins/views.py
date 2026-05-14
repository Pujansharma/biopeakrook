from django.db.models import F, Q, RestrictedError, ProtectedError, Value
from django.db.models.functions import Concat

from core.utils.db.functions import ExtractPartText

from accounts.admins.models import Admin
from accounts.admins.serializers import (
    AdminUserSerializer,
    AdminUserDetailSerializer,
    AdminProfileSerializer,
)
from accounts.utils.permissions import IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseRetrieveUpdateAPIView,
)


class AdminUserView(BaseListCreateAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search_query = Q()
        filter_kwargs = {}
        search_param = self.request.query_params.get("search", "").strip()
        active_param = self.request.query_params.get("active", None)
        if active_param and active_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_param))
        if search_param:
            search_query |= Q(user__email__istartswith=search_param)
            search_query |= Q(national_phone__istartswith=search_param)
            search_query |= Q(full_name__istartswith=search_param)

        return (
            Admin.objects.select_related("user")
            .annotate(
                national_phone=ExtractPartText(
                    F("contact_phone"), Value("-"), Value("-1")
                ),
                full_name=Concat(
                    F("user__first_name"), Value(" "), F("user__last_name")
                ),
            )
            .filter(search_query, **filter_kwargs)
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminUserDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = AdminUserDetailSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Admin.objects.select_related("user", "created_by")

    def get_object(self):
        qs = self.get_queryset()
        return get_object_or_404(qs, pk=self.kwargs.get("pk"))

    def perform_destroy(self, instance: Admin):
        user = instance.user
        if user.pk == self.request.user.pk:
            self.raise_permission_denied("You are not allowed to perform this action")
        try:
            user.delete()
        except RestrictedError, ProtectedError:
            self.raise_bad_request(f"This admin cannot be deleted")


class AdminProfileView(BaseRetrieveUpdateAPIView):
    """View for admins to retrieve and update their own profile"""

    permission_classes = [IsAdminUser]
    serializer_class = AdminProfileSerializer

    def get_object(self):
        # TODO: Remove this logic, here an admin model is being created if it does not exist
        instance, _ = Admin.objects.select_related("user__account").get_or_create(
            user=self.request.user
        )
        return instance
