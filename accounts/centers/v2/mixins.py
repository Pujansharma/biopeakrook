from accounts.centers.models import Center
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from core.utils.exceptions import get_object_or_404


class CenterV2Mixin:
    """Resolve URL center with tenant checks for center-scoped v2 APIs."""

    def get_center_id(self):
        return self.kwargs["pk"]

    def get_center(self):
        center_id = self.get_center_id()
        centers = Center.objects.filter(is_active=True)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            centers = centers.filter(
                associate_assignments__associate=self.request.user.associate,
                associate_assignments__is_active=True,
            )
            header_center_id = getattr(self.request, "center_id", None)
            if header_center_id is None:
                header_center_id = self.request.headers.get("X-Center-ID")
            if str(header_center_id) != str(center_id):
                self.raise_bad_request(
                    "X-Center-ID must match the center in the URL."
                )
        return get_object_or_404(
            centers.distinct(),
            "No valid center found with the given ID.",
            pk=center_id,
        )

    def get_active_query_filter(self):
        filter_kwargs = {}
        active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            filter_kwargs["is_active"] = bool(int(active_query))
        return filter_kwargs
