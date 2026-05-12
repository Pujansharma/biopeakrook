from accounts.organizations.models import Organization, OrganizationType
from accounts.organizations.serializers import OrganizationSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.views.main import BaseRetrieveAPIView, BaseRetrieveUpdateAPIView


class OrganizationSummaryView(BaseRetrieveAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        organization, _ = Organization.objects.get_or_create(
            organization_type=OrganizationType.PLATFORM
        )
        return organization


class OrganizationDetailView(BaseRetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        organization, _ = Organization.objects.get_or_create(
            organization_type=OrganizationType.PLATFORM
        )
        return organization
