from uuid import UUID

from django.db.models import Count, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)
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


def active_role_links_prefetch():
    return Prefetch(
        "role_links",
        queryset=AssociateCenterAssignmentRole.objects.filter(
            is_active=True,
            role__is_active=True,
        ).select_related("role"),
    )


def assignment_active_roles(assignment):
    if assignment is None:
        return []
    roles = []
    for link in assignment.role_links.all():
        if not link.is_active:
            continue
        if not link.role.is_active:
            continue
        roles.append(link.role)
    return roles


def assignment_holds_role(assignment, role_id):
    role_key = str(role_id)
    for role in assignment_active_roles(assignment):
        if str(role.pk) == role_key:
            return True
    return False


def resolve_center_roles(center, role_ids):
    if not role_ids:
        return []
    roles = list(
        AssociateRole.objects.filter_active(
            Q(pk__in=role_ids) & (Q(is_system=True) | Q(center=center))
        )
    )
    found_ids = {role.pk for role in roles}
    missing_ids = set(role_ids) - found_ids
    if missing_ids:
        raise serializers.ValidationError(
            {
                "role_ids": (
                    "Invalid or inactive roles for this center: "
                    f"{', '.join(str(role_id) for role_id in missing_ids)}"
                )
            }
        )
    return roles


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
