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
    """
    Return all live care-team members at this center.

    Members matching service roles fill those seats; others are extras.
    Missing service roles are filled later by associate search — not a 400 here.
    `assignment` kept for call-site compatibility.
    """
    del assignment
    team = load_active_center_care_team(center, care_team_id)
    members = members_with_live_center_role(center, list(team.members.all()))
    members.sort(key=care_team_member_role_sort_key)
    return members


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


def live_members_for_care_team(center, care_team):
    members = list(
        care_team.members.select_related("associate", "role", "care_team").all()
    )
    return members_with_live_center_role(center, members)


def live_associates_for_care_team(center, care_team):
    return [member.associate for member in live_members_for_care_team(center, care_team)]


def live_care_teams_for_associate(center, associate):
    memberships = list(
        CenterCareTeamMember.objects.filter(
            associate=associate,
            care_team__center=center,
            care_team__is_active=True,
        ).select_related("care_team", "role", "associate")
    )
    live_members = members_with_live_center_role(center, memberships)
    care_teams = []
    seen_ids = set()
    for member in live_members:
        care_team_id = member.care_team.pk
        if care_team_id in seen_ids:
            continue
        seen_ids.add(care_team_id)
        care_teams.append(member.care_team)
    return care_teams


def apply_care_team_to_resource_pools(resource_pools, members):
    member_by_role = {str(member.role.pk): member.associate for member in members}
    for role_pool in resource_pools["roles"]:
        associate = member_by_role.get(role_pool["role_id"])
        if associate is None:
            role_pool["associates"] = []
            continue
        role_pool["associates"] = [associate]
