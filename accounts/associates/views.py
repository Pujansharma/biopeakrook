from django.db.models import Q, OuterRef, Exists, RestrictedError, ProtectedError

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.associates.serializers import AssociateSerializer, AssociateCenterLinkSerializer
from accounts.centers.models import Center
from accounts.centers.serializers import CenterSerializer, AssociateAvailableCenterSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView, BaseCreateAPIView, BaseListAPIView
)


class AssociateView(BaseListCreateAPIView):
    """Endpoint to create and list all associates"""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateSerializer

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search_query |= Q(
                user__email__istartswith=search_params
            ) | Q(
                user__phone__istartswith=search_params
            ) | Q(
                user__first_name__istartswith=search_params
            )

        return Associate.objects.select_related().filter(search_query)


class AssociateDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Endpoint to view details for any associate"""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateSerializer

    def get_queryset(self):
        return Associate.objects.select_related()

    def perform_destroy(self, instance: Associate):
        user = instance.user
        try:
            user.delete()
        except (RestrictedError, ProtectedError) as e:
            restricted_count = len(getattr(e, 'restricted_objects', set()))
            protected_count = len(getattr(e, 'protected_objects', set()))
            total = restricted_count + protected_count
            return self.send_bad_request(
                f'Cannot delete this associate. {total} related record(s) exist.'
            )


class AssociateAvailableCenterView(BaseListAPIView):
    """View to list centers available for any associate"""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateAvailableCenterSerializer

    def get_associate(self):
        associate_id = self.kwargs.get('pk')
        qs = Associate.objects.select_related().filter()
        return get_object_or_404(qs, pk=associate_id)

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search_query |= Q(name__istartswith=search_params) | Q(
                code__istartswith=search_params
            ) | Q(
                code__icontains=search_params
            ) | Q(
                name__icontains=search_params
            )
        associate = self.get_associate()
        associated_centers_subquery = AssociateCenterAssignment.objects.filter(
            associate=associate,
            center=OuterRef('pk')
        )
        return Center.objects.annotate(
            exists=Exists(associated_centers_subquery)
        ).filter(search_query)


class AssociateCenterLinkView(BaseCreateAPIView):
    """View to link or delink associates to a center"""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateCenterLinkSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get('pk')
        )

    def perform_create(self, serializer):
        associate = self.get_associate()
        serializer.save(associate=associate)


class AssociateAssignedCenters(BaseListAPIView):
    """View to list the centers assigned to an associate"""
    permission_classes = [IsAdminUser]
    serializer_class = CenterSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get('pk')
        )

    def get_queryset(self):
        associate = self.get_associate()
        return Center.objects.select_related().filter(
            associate_assignments__associate=associate
        )
