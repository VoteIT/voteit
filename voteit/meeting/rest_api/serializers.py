from __future__ import annotations
from contextlib import suppress
from typing import Optional
from typing import Type

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.core.models import Roles
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.core.rest_api.utils import meeting_from_unsafe_data
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingComponent
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.utils import get_meeting_component_adapters


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
        model = Meeting
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
        model = Meeting
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
        model = MeetingRoles
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
        model = MeetingRoles
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
        max_length=20, validators=[RoleValidator(roles_cls=MeetingRoles)]
    )


class MeetingGroupSerializer(BaseModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = MeetingGroup
        exclude = ("id",)


class CreateMeetingComponentSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = MeetingComponent
        exclude = ("id", "settings_data")
        read_only_fields = ["state"]

    def validate_component_name(self, value: str):
        registry = get_meeting_component_adapters()
        if value not in registry:
            raise ValidationError("No such meeting component")
        # Will raise error if meeting doesn't exist
        component_adapter = registry[value]
        if not component_adapter.multiple:
            meeting = meeting_from_unsafe_data(self)
            if meeting.components.filter(component_name=value).exists():
                raise ValidationError(
                    "Only one of these components are allowed per meeting."
                )
        return value


class MeetingComponentSerializer(CreateMeetingComponentSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta(CreateMeetingComponentSerializer.Meta):
        read_only_fields = [
            "component_name",
            "meeting",
        ] + CreateMeetingComponentSerializer.Meta.read_only_fields

    def validate_settings(self, value):
        schema = self.instance.component.schema
        if schema:
            try:
                schema(**value)
            except ValueError as exc:
                # Better than nothing!
                raise ValidationError(str(exc))
        else:
            # No schema, so no values are allowed!
            if value is not None:
                raise ValidationError("Component has no schema, so no settings allowed")
        return value


class VerboseMeetingComponentSerializer(MeetingComponentSerializer):
    schema = serializers.SerializerMethodField()

    def get_schema(self, instance: MeetingComponent):
        if instance.component and instance.component.schema is not None:
            return instance.component.schema.schema()
