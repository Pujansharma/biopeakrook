from django.db.models import Q, RestrictedError, ProtectedError

from accounts.admins.models import Admin
from accounts.admins.serializers import AdminUserSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView


class AdminUserView(BaseListCreateAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search_query = Q()
        search_param = self.request.query_params.get('search', '').strip()
        if search_param:
            search_query |= Q(user__email__istartswith=search_param)
            search_query |= Q(user__phone__istartswith=search_param)
            search_query |= Q(user__first_name__istartswith=search_param)

        return Admin.objects.select_related('user').exclude(
            user=self.request.user
        ).filter(search_query)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminUserDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Admin.objects.select_related('user').exclude(user=self.request.user)

    def get_object(self):
        qs = self.get_queryset()
        return get_object_or_404(qs, pk=self.kwargs.get('pk'))

    def perform_destroy(self, instance: Admin):
        user = instance.user
        try:
            user.delete()
        except (RestrictedError, ProtectedError) as e:
            restricted_count = len(getattr(e, 'restricted_objects', set()))
            protected_count = len(getattr(e, 'protected_objects', set()))
            total = restricted_count + protected_count
            self.raise_bad_request(f'Cannot delete this admin. {total} related record(s) exist.')
