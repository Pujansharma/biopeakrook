from django.db.models import Prefetch, Q
from rest_framework import serializers

from accounts.associates.models import (
    AssociateCenterAssignment,
    AssociateCenterAssignmentRole,
    AssociateRole,
)


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
    cached = getattr(assignment, "_assignment_active_roles", None)
    if cached is not None:
        return cached
    roles = []
    for link in assignment.role_links.all():
        if not link.is_active:
            continue
        if not link.role.is_active:
            continue
        roles.append(link.role)
    assignment._assignment_active_roles = roles
    return roles


def assignment_for_center(associate, center_id):
    """Pick associate×center assignment from prefetched `center_assignments`."""
    if associate is None or center_id is None:
        return None
    for assignment in associate.center_assignments.all():
        if assignment.center_id == center_id:
            return assignment
    return None


def associate_center_assignments_prefetch():
    """Prefetch center assignments + active role links (safe w/o FilteredRelation)."""
    return Prefetch(
        "associate__center_assignments",
        queryset=AssociateCenterAssignment.objects.prefetch_related(
            active_role_links_prefetch()
        ),
    )


def assignment_holds_role(assignment, role_id):
    role_key = str(role_id)
    for role in assignment_active_roles(assignment):
        if str(role.pk) == role_key:
            return True
    return False


def resolve_center_roles(center, role_ids, field_name="role_ids"):
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
                field_name: (
                    "Invalid or inactive roles for this center: "
                    f"{', '.join(str(role_id) for role_id in missing_ids)}"
                )
            }
        )
    return roles
