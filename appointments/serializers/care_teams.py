from django.db import transaction
from django.db.models import Prefetch
from rest_framework import serializers

from accounts.associates.models import AssociateCenterAssignment, AssociateRole
from appointments.models import CenterCareTeam, CenterCareTeamMember
from appointments.utils.scheduling import get_associate_display_name
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class CareTeamAssociateNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.SerializerMethodField()

    def get_name(self, obj):
        return get_associate_display_name(obj)


class CareTeamRoleNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()


class CenterCareTeamMemberNestedSerializer(BaseModelSerializer):
    associate = CareTeamAssociateNestedSerializer(read_only=True)
    role = CareTeamRoleNestedSerializer(read_only=True)

    class Meta:
        model = CenterCareTeamMember
        fields = ["associate", "role"]


class CenterCareTeamMemberInputSerializer(BaseSerializer):
    associate_id = serializers.UUIDField()
    role_id = serializers.UUIDField()


def prefetched_care_team_queryset():
    return CenterCareTeam.objects.prefetch_related(
        Prefetch(
            "members",
            queryset=CenterCareTeamMember.objects.select_related(
                "associate__user",
                "role",
            ).order_by("role"),
            to_attr="prefetched_members",
        )
    )


class CenterCareTeamSerializer(BaseModelSerializer):
    members = CenterCareTeamMemberInputSerializer(
        many=True, required=False, write_only=True
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

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        member_rows = getattr(instance, "prefetched_members", [])
        representation["members"] = CenterCareTeamMemberNestedSerializer(
            member_rows, many=True
        ).data
        return representation

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
        assignments = AssociateCenterAssignment.objects.filter(
            center=center,
            is_active=True,
            associate__is_active=True,
            associate__pk__in=associate_ids,
        ).select_related("associate", "role")
        assignment_by_associate = {
            assignment.associate.pk: assignment for assignment in assignments
        }
        for entry in members:
            assignment = assignment_by_associate.get(entry["associate_id"])
            if assignment is None or assignment.role.pk != entry["role_id"]:
                raise serializers.ValidationError(
                    {
                        "members": [
                            "Associate is not assigned to this center with the required role."
                        ]
                    }
                )
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
        members = attrs.get("members")
        creating = self.instance is None
        members_in_payload = "members" in getattr(self, "initial_data", {})
        if creating and not members:
            raise serializers.ValidationError(
                {"members": ["A care team must have at least two members."]}
            )
        if members_in_payload:
            attrs["members"] = self.validate_members_payload(members or [])
        return attrs

    def replace_members(self, care_team, members):
        CenterCareTeamMember.objects.filter(care_team=care_team).delete()
        CenterCareTeamMember.objects.bulk_create(
            [
                CenterCareTeamMember(
                    care_team=care_team,
                    associate_id=entry["associate_id"],
                    role_id=entry["role_id"],
                )
                for entry in members
            ]
        )
        care_team.members_count = len(members)
        care_team.save(update_fields=["members_count", "updated_at"])

    def reload_team(self, care_team):
        return prefetched_care_team_queryset().filter(pk=care_team.pk).first()

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
        return self.reload_team(care_team)

    def update(self, instance, validated_data):
        members = validated_data.pop("members", None)
        members_in_payload = "members" in getattr(self, "initial_data", {})
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if members_in_payload:
                self.replace_members(instance, members)
        return self.reload_team(instance)
