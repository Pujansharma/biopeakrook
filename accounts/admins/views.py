from django.db.models import Q, RestrictedError, ProtectedError

from accounts.admins.models import Admin
from accounts.admins.serializers import AdminUserSerializer, AdminUserDetailSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)


class AdminUserView(BaseListCreateAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search_query = Q()
        filter_kwargs = {}
        search_param = self.request.query_params.get("search", "").strip()
        active_param = self.request.query_params.get("is_active", None)
        if active_param is not None:
            filter_kwargs["is_active"] = bool(int(active_param))
        if search_param:
            search_query |= Q(user__email__istartswith=search_param)
            search_query |= Q(user__phone__istartswith=search_param)
            search_query |= Q(user__first_name__istartswith=search_param)

        return Admin.objects.select_related("user").filter(
            search_query, **filter_kwargs
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
