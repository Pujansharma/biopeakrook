from django.db.models import Q

from accounts.associates.models import Associate
from accounts.associates.serializers import AssociateSerializer
from accounts.utils.permissions import IsAdminUser
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
            search_query |= Q()

        return Associate.objects.select_related().filter(search_query)


class AssociateDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Endpoint to view details for any associate"""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateSerializer

    def get_queryset(self):
        pass


class AssociateAvailableCenterView(BaseListAPIView):
    """View to list centers available for any associate"""
    pass


class AssociateCenterLinkView(BaseCreateAPIView):
    """View to link or delink associates to a center"""
    pass


class AssociateAssignedCenters(BaseListAPIView):
    """View to list the centers assigned to an associate"""
    pass
