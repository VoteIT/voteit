from __future__ import annotations
from contextlib import suppress
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.core.models import Roles
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.meeting import models

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


class UserRolesMixin(serializers.Serializer):
    current_user_roles = serializers.SerializerMethodField()

    def get_current_user_roles(self, instance) -> Optional[list[str]]:
        """
        Return current user roles, if available, for a meeting.
        """
        if self.context:
            user = self.context["request"].user
            with suppress(ObjectDoesNotExist):
                return instance.roles.get(user=user).assigned


class MeetingSerializer(UserRolesMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = models.Meeting
        fields = read_only_fields = (
            "url",
            "pk",
            "title",
            "state",
            "start_time",
            "end_time",
            "public",
            "visible_in_lists",
            "current_user_roles",
        )


class MeetingDetailSerializer(UserRolesMixin, BaseModelSerializer):
    class Meta:
        model = models.Meeting
        read_only_fields = [
            "pk",
            "state",
            "start_time",
            "end_time",
            "organisation",
            "current_user_roles",
            "public",
        ]
        fields = read_only_fields + [
            "title",
            "body",
            "er_policy_name",
            "visible_in_lists",
        ]

    def create(self, validated_data):
        user = self.get_request_user()
        if user.organisation is not None:
            validated_data["organisation"] = user.organisation
        return super().create(validated_data)

    def validate_er_policy_name(self, value):
        from voteit.poll.workflows import PollWf

        if self.instance is not None:
            self.instance: Meeting
            if self.instance.polls.filter(state=PollWf.ONGOING).exists():
                raise ValidationError(
                    "There are ongoing polls - close them before changing policy."
                )
        return value


class AgendaOrderSerializer(serializers.Serializer):
    order = serializers.ListSerializer(child=serializers.IntegerField())


class MeetingRolesSerializer(serializers.ModelSerializer):
    meeting = serializers.IntegerField(source="context_id", read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = models.MeetingRoles
        fields = read_only_fields = (
            "pk",
            "user",
            "meeting",
            "assigned",
        )


class MeetingAddParticipantSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField()
    meeting_id = serializers.IntegerField(source="context_id")

    class Meta:
        model = models.MeetingRoles
        fields = "user_id", "meeting_id"


class RoleValidator:
    """Ensures that role name is valid for roles class provided on class instantiation."""

    roles_cls: Type[Roles]

    def __init__(self, roles_cls: Type[Roles]):
        self.roles_cls = roles_cls

    def __call__(self, value):
        if value not in self.roles_cls.valid_roles:
            raise ValidationError(f'The role "{value}" is not valid for this context.')


class RoleSerializer(serializers.Serializer):
    role = serializers.CharField(
        max_length=20, validators=[RoleValidator(roles_cls=models.MeetingRoles)]
    )


class MeetingGroupSerializer(BaseModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.MeetingGroup
        fields = "__all__"
