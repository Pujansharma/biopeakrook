from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from accounts.associates.models import AssociateCenterAssignment
from appointments.models import CenterCareTeam, CenterCareTeamMember


def load_active_center_care_team(center, care_team_id):
    team = (
        CenterCareTeam.objects.filter(
            pk=care_team_id,
            center=center,
            is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "members",
                queryset=CenterCareTeamMember.objects.select_related(
                    "associate__user",
                    "role",
                    "care_team",
                ).order_by("role"),
            )
        )
        .first()
    )
    if team is None:
        raise ValidationError("Care team is invalid or inactive.")
    return team


def care_team_member_role_sort_key(member):
    return str(member.role.pk)


def live_associate_center_assignments(center, associate_ids):
    return AssociateCenterAssignment.objects.filter(
        center=center,
        is_active=True,
        associate__user__is_active=True,
        role__is_active=True,
        associate__pk__in=associate_ids,
    ).select_related("associate", "role")


def members_with_live_center_role(center, members):
    associate_ids = [member.associate.pk for member in members]
    assignments_by_associate = {
        center_assignment.associate.pk: center_assignment
        for center_assignment in live_associate_center_assignments(
            center, associate_ids
        )
    }
    eligible_members = []
    for member in members:
        center_assignment = assignments_by_associate.get(member.associate.pk)
        if center_assignment is None:
            continue
        if center_assignment.role.pk != member.role.pk:
            continue
        eligible_members.append(member)
    return eligible_members


def expand_care_team_for_assignment(center, care_team_id, assignment):
    team = load_active_center_care_team(center, care_team_id)
    role_requirements = list(
        assignment.role_requirements.filter(is_active=True)
    )
    if not role_requirements:
        raise ValidationError(
            "Care team allocation is only valid when the service requires staff."
        )
    required_role_ids = {requirement.role.pk for requirement in role_requirements}
    members = members_with_live_center_role(center, list(team.members.all()))
    team_role_ids = {member.role.pk for member in members}
    if required_role_ids - team_role_ids:
        raise ValidationError(
            "Care team does not cover all required service roles."
        )
    required_members = [
        member for member in members if member.role.pk in required_role_ids
    ]
    required_members.sort(key=care_team_member_role_sort_key)
    return required_members


def care_team_associates_payload(members):
    payload = []
    for member in members:
        payload.append(
            {
                "role_id": str(member.role.pk),
                "associate_id": member.associate.pk,
            }
        )
    return payload


def apply_care_team_to_resource_pools(resource_pools, members):
    member_by_role = {str(member.role.pk): member.associate for member in members}
    for role_pool in resource_pools["roles"]:
        associate = member_by_role.get(role_pool["role_id"])
        if associate is None:
            role_pool["associates"] = []
            continue
        role_pool["associates"] = [associate]
