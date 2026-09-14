from uuid import UUID

from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
)
from accounts.associates.utils.roles import active_role_links_prefetch
from accounts.models import UserAccount
from accounts.utils.constants import UserType


def create_associate_user_account(associate):
    """Creates a user account for Associate user type."""
    user = associate.user
    user_account, _ = UserAccount.objects.update_or_create(
        user=user, account_type=UserType.ASSOCIATE
    )
    return user_account


def update_associate_centers_count(associate_id: UUID):
    centers_count_subquery = Subquery(
        AssociateCenterAssignment.objects.filter(associate=OuterRef("pk"))
        .order_by()
        .values("associate")
        .annotate(count=Count("center", distinct=True))
        .values("count")
    )
    return Associate.objects.filter(pk=associate_id).update(
        centers_count=Coalesce(centers_count_subquery, Value(0))
    )


def update_center_associate_centers_count(center_id: UUID):
    centers_count_subquery = Subquery(
        AssociateCenterAssignment.objects.filter(associate=OuterRef("pk"))
        .exclude(center__pk=center_id)
        .order_by()
        .values("associate")
        .annotate(count=Count("center", distinct=True))
        .values("count")
    )
    return Associate.objects.filter(
        center_assignments__center__pk=center_id
    ).update(centers_count=Coalesce(centers_count_subquery, Value(0)))


def replace_assignment_roles(assignment, roles):
    AssociateCenterAssignmentRole.objects.filter(assignment=assignment).delete()
    if not roles:
        return
    AssociateCenterAssignmentRole.objects.bulk_create(
        [
            AssociateCenterAssignmentRole(
                assignment=assignment,
                role_id=role.pk,
            )
            for role in roles
        ]
    )


def get_associate_roles(associate, center_id, request=None):
    cache_key = "_center_assignment"

    if request and hasattr(request, cache_key):
        return getattr(request, cache_key)

    assignment = (
        AssociateCenterAssignment.objects.filter(
            associate=associate, center_id=center_id, is_active=True
        )
        .prefetch_related(active_role_links_prefetch())
        .first()
    )

    if request:
        setattr(request, cache_key, assignment)

    return assignment


def get_center_assignment_for_user(user, center_id, request=None):
    cache_key = "_center_assignment"

    if request and hasattr(request, cache_key):
        return getattr(request, cache_key)

    assignment = (
        AssociateCenterAssignment.objects.filter(
            associate__user=user, center_id=center_id, is_active=True
        )
        .prefetch_related(active_role_links_prefetch())
        .first()
    )

    if request:
        setattr(request, cache_key, assignment)

    return assignment
