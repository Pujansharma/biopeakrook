from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from accounts.associates.models import AssociateCenterAssignment
from accounts.associates.utils.roles import (
    active_role_links_prefetch,
    assignment_holds_role,
)
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
    return (
        AssociateCenterAssignment.objects.filter(
            center=center,
            is_active=True,
            associate__user__is_active=True,
            associate__pk__in=associate_ids,
            role_links__is_active=True,
            role_links__role__is_active=True,
        )
        .select_related("associate", "associate__user")
        .prefetch_related(active_role_links_prefetch())
        .distinct()
    )


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
        if not assignment_holds_role(center_assignment, member.role.pk):
            continue
        eligible_members.append(member)
    return eligible_members


def expand_care_team_for_assignment(center, care_team_id):
    """
    Return all live care-team members at this center.

    Member role must be among the associate's live multi-roles at the center.
    """
    team = load_active_center_care_team(center, care_team_id)
    members = members_with_live_center_role(center, list(team.members.all()))
    members.sort(key=care_team_member_role_sort_key)
    return members


def live_members_for_care_team(center, care_team):
    members = list(care_team.members.all())
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
