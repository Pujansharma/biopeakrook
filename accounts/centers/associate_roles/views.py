from accounts.associates.models import AssociateRole
from accounts.associates.serializers import AssociateRoleSerializer
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAssociateUser, IsAdminUser
from core.utils.exceptions import get_object_or_404
from core.utils.views import BaseRetrieveUpdateDestroyAPIView


class AssociateCenterRoleDetailView(BaseRetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        user = self.request.user
        filter_kwargs = {}

        account_type = get_user_account_type(user)
        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate

        return AssociateRole.objects.select_related("created_by").filter(
            **filter_kwargs
        )

    def get_object(self):
        qs = self.get_queryset()
        return get_object_or_404(qs, "Associate role not found", pk=self.kwargs["pk"])
