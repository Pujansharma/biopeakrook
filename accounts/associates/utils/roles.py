from django.db.models import Prefetch, Q
from rest_framework import serializers

from accounts.associates.models import AssociateCenterAssignmentRole, AssociateRole


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
