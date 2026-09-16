from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.associates.models import AssociateRole
from accounts.associates.utils.roles import assignment_holds_role
from appointments.models import (
    CareTeamAvailabilityBlock,
    CenterCareTeam,
    CenterCareTeamMember,
)
from appointments.utils.care_teams import live_associate_center_assignments
from appointments.utils.constants import ExceptionSourceType
from appointments.utils.exceptions import resolve_exceptions_for_source
from appointments.utils.scheduling import get_associate_display_name
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class CareTeamAssociateNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()

    def get_name(self, obj):
        return get_associate_display_name(obj)


class CareTeamRoleNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class CenterCareTeamMemberNestedSerializer(BaseModelSerializer):
    associate = CareTeamAssociateNestedSerializer(read_only=True)
    role = CareTeamRoleNestedSerializer(read_only=True)

    class Meta:
        model = CenterCareTeamMember
        fields = ["associate", "role"]


class CenterCareTeamMemberInputSerializer(BaseSerializer):
    associate_id = serializers.UUIDField()
    role_id = serializers.UUIDField()


class CenterCareTeamSerializer(BaseModelSerializer):
    members = CenterCareTeamMemberNestedSerializer(
        many=True, read_only=True, source="prefetched_members"
    )
    members_count = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = CenterCareTeam
        fields = [
            "id",
            "name",
            "is_active",
            "members_count",
            "members",
            "created_at",
            "updated_at",
        ]

    def parse_members_payload(self):
        member_serializer = CenterCareTeamMemberInputSerializer(
            data=self.initial_data.get("members") or [],
            many=True,
        )
        if not member_serializer.is_valid():
            raise serializers.ValidationError({"members": member_serializer.errors})
        return self.validate_members_payload(member_serializer.validated_data)

    def validate_members_payload(self, members):
        if len(members) < 2:
            raise serializers.ValidationError(
                {"members": ["A care team must have at least two members."]}
            )
        associate_ids = [entry["associate_id"] for entry in members]
        role_ids = [entry["role_id"] for entry in members]
        if len(set(associate_ids)) != len(associate_ids):
            raise serializers.ValidationError(
                {"members": ["Each associate may appear only once on a team."]}
            )
        if len(set(role_ids)) != len(role_ids):
            raise serializers.ValidationError(
                {"members": ["Each role may appear only once on a team."]}
            )
        center = self.context["center"]
        roles = {
            role.pk: role
            for role in AssociateRole.objects.filter(pk__in=role_ids, center=center)
        }
        invalid_roles = [role_id for role_id in role_ids if role_id not in roles]
        if invalid_roles:
            raise serializers.ValidationError(
                {"members": ["Role does not belong to this center."]}
            )
        inactive_roles = [
            role_id for role_id in role_ids if not roles[role_id].is_active
        ]
        if inactive_roles:
            raise serializers.ValidationError(
                {"members": ["Role is inactive."]}
            )
        assignments = live_associate_center_assignments(center, associate_ids)
        assignment_by_associate = {
            assignment.associate.pk: assignment for assignment in assignments
        }
        for entry in members:
            assignment = assignment_by_associate.get(entry["associate_id"])
            member_role = roles.get(entry["role_id"])
            if assignment is None or member_role is None:
                raise serializers.ValidationError(
                    {
                        "members": [
                            "Associate is not assigned to this center with the required role."
                        ]
                    }
                )
            if not assignment_holds_role(assignment, entry["role_id"]):
                raise serializers.ValidationError(
                    {
                        "members": [
                            "Associate is not assigned to this center with the required role."
                        ]
                    }
                )
            entry["associate"] = assignment.associate
            entry["role"] = member_role
        return members

    def validate(self, attrs):
        center = self.context["center"]
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name:
            clash = CenterCareTeam.objects.filter(center=center, name__iexact=name)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "name": [
                            "A care team with this name already exists at this center."
                        ]
                    }
                )
        members_in_payload = "members" in getattr(self, "initial_data", {})
        creating = self.instance is None
        if creating and not members_in_payload:
            raise serializers.ValidationError(
                {"members": ["A care team must have at least two members."]}
            )
        if members_in_payload:
            attrs["members"] = self.parse_members_payload()
        return attrs

    def replace_members(self, care_team, members):
        CenterCareTeamMember.objects.filter(care_team=care_team).delete()
        CenterCareTeamMember.objects.bulk_create(
            [
                CenterCareTeamMember(
                    care_team=care_team,
                    associate=entry["associate"],
                    role=entry["role"],
                )
                for entry in members
            ]
        )
        care_team.members_count = len(members)
        care_team.save(update_fields=["members_count", "updated_at"])

    def create(self, validated_data):
        members = validated_data.pop("members")
        center = validated_data.pop("center")
        created_by = validated_data.pop("created_by", None)
        with transaction.atomic():
            care_team = CenterCareTeam.objects.create(
                center=center,
                created_by=created_by,
                members_count=len(members),
                **validated_data,
            )
            self.replace_members(care_team, members)
        return care_team

    def update(self, instance, validated_data):
        members = validated_data.pop("members", None)
        members_in_payload = "members" in getattr(self, "initial_data", {})
        was_active = instance.is_active
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if members_in_payload:
                self.replace_members(instance, members)
            if was_active and not instance.is_active:
                block_ids = list(
                    CareTeamAvailabilityBlock.objects.filter(
                        care_team=instance,
                        is_active=True,
                    ).values_list("pk", flat=True)
                )
                if block_ids:
                    CareTeamAvailabilityBlock.objects.filter(pk__in=block_ids).update(
                        is_active=False, updated_at=timezone.now()
                    )
                    for block_id in block_ids:
                        resolve_exceptions_for_source(
                            ExceptionSourceType.CARE_TEAM_BLOCK,
                            block_id,
                        )
        return instance
