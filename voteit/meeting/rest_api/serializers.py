from __future__ import annotations

from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueTogetherValidator

from voteit.core.rest_api.fields import RolesField
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import UserListSerializer
from voteit.core.rest_api.utils import meeting_from_unsafe_data
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.validators import RoleValidator
from voteit.meeting.rest_api.validators import DialectInstallableValidator
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.poll.utils import get_electoral_policy_registry
from voteit.room.rest_api.serializers import CreateRoomSerializer
from voteit.speaker.rest_api.serializers import CreateSpeakerListSystemSerializer

if TYPE_CHECKING:
    from voteit.poll.abcs import ElectoralRegisterPolicy

__all__ = (
    "UserRolesMixin",
    "MeetingSerializer",
    "CreateMeetingSerializer",
    "MeetingDetailSerializer",
    "AgendaOrderSerializer",
    "MeetingRolesSerializer",
    "MeetingAddParticipantSerializer",
    "RoleSerializer",
    "MeetingGroupSerializer",
    "GroupRoleSerializer",
    "GroupMembershipSerializer",
    "ParticipantExportSerializer",
)

logger = getLogger(__name__)


class UserRolesMixin(serializers.Serializer):
    current_user_roles = serializers.SerializerMethodField()

    def get_current_user_roles(self, instance) -> list[str] | None:
        """
        Return current user roles, if available, for a meeting.
        user_roles should be annotated as 'assigned' from MeetingRoles
        """
        if hasattr(instance, "user_roles"):
            # Empty arrays in JS is true...
            return instance.user_roles or None
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


def validate_er_policy_name(instance: Meeting | None, value: str | None):
    if value:
        reg = get_electoral_policy_registry()
        if value not in reg:
            raise ValidationError(f"No electoral register policy named {value}")
        er_policy: ElectoralRegisterPolicy = reg[value]
        if not er_policy.available:
            # If meeting has no dialect, ER policy isn't available
            if instance is None or instance.installed_dialect is None:
                raise_dialect_only(value)
            handler = dialect_registry.get_merged_handler(instance.installed_dialect)
            # Check if meeting dialect suggests selected ER policy
            if handler.data.er_policy_name != value:
                raise_dialect_only(value)
        # ER policy requiring group_votes_active must have a meeting
        if er_policy.group_votes_active and instance is None:
            raise_dialect_only(value)
        # This is only valid for subclasses so maybe move later
        if (
            instance
            and er_policy.group_votes_active is not None
            and instance.group_votes_active != er_policy.group_votes_active
        ):
            raise ValidationError(
                f"Policy '{value}' is not compatible with the meetings group votes setting"
            )
        return value


def raise_dialect_only(value: str):
    raise ValidationError(
        f"Policy '{value}' isn't manually selectable, it must be installed via a meeting dialect"
    )


class CreateRoomOnMeetingSerializer(CreateRoomSerializer):
    class Meta(CreateRoomSerializer.Meta):
        fields = [x for x in CreateRoomSerializer.Meta.fields if x not in ["meeting"]]


class CreateSpeakerListSystemOnMeetingSerializer(CreateSpeakerListSystemSerializer):
    class Meta(CreateSpeakerListSystemSerializer.Meta):
        fields = [
            x
            for x in CreateSpeakerListSystemSerializer.Meta.fields
            if x not in ["meeting", "room"]
        ]


class CreateMeetingSerializer(BaseModelSerializer):
    instance: Meeting | None
    install_dialect = serializers.CharField(
        validators=[DialectInstallableValidator()],
        required=False,
    )
    room = CreateRoomOnMeetingSerializer(required=False)
    sls = CreateSpeakerListSystemOnMeetingSerializer(required=False)

    class Meta:
        model = Meeting
        # FIXME: Which fields do we allow changes to here?
        read_only_fields = [
            "pk",
        ]
        fields = read_only_fields + [
            "title",
            "body",
            "er_policy_name",
            "visible_in_lists",
            "install_dialect",
            "room",
            "sls",
        ]

    def create(self, validated_data):
        user = self.get_request_user()
        if user.organisation is not None:
            validated_data["organisation"] = user.organisation
        with transaction.atomic(durable=True):
            install_dialect = validated_data.pop("install_dialect", None)
            room_data = validated_data.pop("room", None)
            sls_data = validated_data.pop("sls", None)
            instance = super().create(validated_data)
            instance.add_roles(user, ROLE_MODERATOR)
            if install_dialect:
                handler = dialect_registry.get_merged_handler(install_dialect)
                handler.install(instance)
            if room_data:
                room_serializer = CreateRoomSerializer(
                    data={"meeting": instance.pk, **room_data},
                    context=self.context,
                )
                room_serializer.is_valid(raise_exception=True)
                room = room_serializer.save()
                if sls_data:
                    sls_serializer = CreateSpeakerListSystemSerializer(
                        data={"meeting": instance.pk, "room": room.pk, **sls_data},
                        context=self.context,
                    )
                    sls_serializer.is_valid(raise_exception=True)
                    sls_serializer.save()
            return instance

    def validate_er_policy_name(self, value):
        return validate_er_policy_name(self.instance, value)


class MeetingDetailSerializer(UserRolesMixin, BaseModelSerializer):
    dialect = serializers.SerializerMethodField()

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
            "installed_dialect",
            "dialect",
            "group_roles_active",
            "group_votes_active",
            "vote_transfer_policy",
        ]
        fields = read_only_fields + [
            "title",
            "body",
            "er_policy_name",
            "visible_in_lists",
        ]

    def validate_er_policy_name(self, value):
        from voteit.poll.workflows import PollWf

        self.instance: Meeting
        value = validate_er_policy_name(self.instance, value)
        if self.instance.polls.filter(state=PollWf.ONGOING).exists():
            raise ValidationError(
                "There are ongoing polls - close them before changing policy."
            )
        return value

    def get_dialect(self, instance: Meeting) -> dict | None:
        if instance.installed_dialect:
            # May cause key error if something's wrong. We'll probably want that.
            try:
                handler = dialect_registry.get_merged_handler(
                    instance.installed_dialect
                )
            except KeyError:
                logger.error(
                    "Installed meeting dialect %s doesn't exist. Meeting pk: %s",
                    instance.installed_dialect,
                    instance.pk,
                )
            else:
                return handler.data.dict(exclude_unset=True)


class AgendaOrderSerializer(serializers.Serializer):
    order = serializers.ListSerializer(child=serializers.IntegerField())


class MeetingRolesSerializer(serializers.ModelSerializer):
    meeting = serializers.IntegerField(source="context_id", read_only=True)
    user = UserListSerializer(read_only=True)
    assigned = serializers.ListSerializer(child=serializers.CharField())

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


class RoleSerializer(serializers.Serializer):
    role = serializers.CharField(
        max_length=20, validators=[RoleValidator(roles_cls=MeetingRoles)]
    )


class CreateMeetingGroupSerializer(BaseModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    # I have no clue why the normal automation for serializer fields stopped working for this field
    # as of DRF 3.15+
    groupid = serializers.CharField(max_length=100, default="")

    class Meta:
        model = MeetingGroup
        fields = [
            "pk",
            "body",
            "groupid",
            "meeting",
            "tags",
            "title",
            "votes",
            "show_on_speaker",
            "post_as",
        ]

    def validate_groupid(self, value: str | None):
        if value:
            slug = slugify(value)
            if value != slug:
                raise ValidationError("Must be lowercase URL-friendly")
            exclude_pks = []
            if self.instance is not None:
                meeting = self.instance.meeting
                exclude_pks.append(self.instance.pk)
            else:
                meeting = meeting_from_unsafe_data(self)
            if meeting.groups.exclude(pk__in=exclude_pks).filter(groupid=slug).exists():
                raise ValidationError(f"GroupID {slug} already exists")
            return slug
        return value


class MeetingGroupSerializer(CreateMeetingGroupSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta(CreateMeetingGroupSerializer.Meta):
        read_only_fields = [
            "meeting",
        ]
        fields = [
            "pk",
            "body",
            "delegate_to",
            "groupid",
            "tags",
            "title",
            "votes",
            "show_on_speaker",
            "post_as",
        ] + read_only_fields

    def validate_delegate_to(self, value: MeetingGroup | None):
        if value:
            if not isinstance(value, MeetingGroup):
                raise ValidationError("Not a meeting group")
            if self.instance == value:
                raise ValidationError("Delegate to yourself? No.")
            if value.delegate_to_id:
                raise ValidationError("Already delegates to another group.")
            if self.instance.delegations_from.exists():
                raise ValidationError(
                    "Other groups delegates to your group already, clear them first."
                )
        return value


class GroupRoleSerializer(BaseModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    roles = RolesField()

    class Meta:
        model = GroupRole
        exclude = (
            "id",
            "users",
        )


class CreateGroupMembershipSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = GroupMembership
        exclude = ("id",)
        validators = [
            UniqueTogetherValidator(
                queryset=GroupMembership.objects.all(), fields=["meeting_group", "user"]
            )
        ]

    def validate(self, attrs):
        """
        Make sure role (if it exists) is attached to same meeting as meeting_group
        """
        meeting = attrs["meeting_group"].meeting
        user = attrs["user"]
        if not meeting.has_roles(user, ROLE_PARTICIPANT):
            raise ValidationError(
                {"user": "No user with that ID exist in this meeting"}
            )
        role = attrs.get("role", None)
        if role:
            if not meeting.group_roles_active:
                raise ValidationError(
                    {
                        "role": "'group_roles_active' not set on meeting - no roles can be added to users in groups"
                    }
                )

            if role.meeting != meeting:
                raise ValidationError({"role": "Role doesn't exist in this meeting"})
        return attrs


class GroupMembershipSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = GroupMembership
        exclude = ("id",)
        read_only_fields = ["meeting_group", "user", "pk"]

    def validate_role(self, value):
        if value:
            if not self.instance.meeting.group_roles_active:
                raise ValidationError(
                    "'group_roles_active' not set on meeting - no roles can be added to users in groups"
                )
            if value.meeting != self.instance.meeting:
                raise ValidationError("Role doesn't exist in this meeting")
        return value


class MeetingGroupExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingGroup
        fields = [
            "title",
            "groupid",
            "votes",
        ]


class ParticipantExportSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    userid = serializers.CharField()
    moderator = serializers.SerializerMethodField()
    potential_voter = serializers.SerializerMethodField()
    discusser = serializers.SerializerMethodField()
    proposer = serializers.SerializerMethodField()

    def get_moderator(self, roles: MeetingRoles) -> bool:
        return ROLE_MODERATOR in roles.assigned

    def get_potential_voter(self, roles: MeetingRoles) -> bool:
        return ROLE_POTENTIAL_VOTER in roles.assigned

    def get_discusser(self, roles: MeetingRoles) -> bool:
        return ROLE_DISCUSSER in roles.assigned

    def get_proposer(self, roles: MeetingRoles) -> bool:
        return ROLE_PROPOSER in roles.assigned

    class Meta:
        model = MeetingRoles
        exclude = ("id", "assigned", "context", "user")
