from logging import getLogger

from rest_framework import serializers
from rest_framework import exceptions

from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_data_registry
from voteit.core.rest_api.serializers import BaseModelSerializer


logger = getLogger(__name__)


class InviteQuerySerializer(serializers.Serializer):
    scope = serializers.CharField()
    data = serializers.CharField()
    validated = serializers.DateTimeField()

    def validate_scope(self, value):
        if value not in get_invite_data_registry():
            logger.warning(f"No invite scope {value}")
        return value


class CreateMeetingInviteSerializer(BaseModelSerializer):
    author_kw = "created_by"

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created_by",
            "pk",
        ]
        fields = read_only_fields + [
            "invite_data",
            "meeting",
            "roles",
            "type",
        ]
        extra_kwargs = {
            "type": {"default": "email"},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        reg = get_invite_data_registry()
        inv_type = attrs.get("type")
        if inv_type not in reg:
            raise exceptions.ValidationError({"type": [f"Not a valid invite type"]})
        invite_data = attrs["invite_data"].lower()
        try:
            reg[attrs["type"]](**{attrs["type"]: invite_data})
        except ValueError:
            raise exceptions.ValidationError(
                {"invite_data": [f"{invite_data} is not a valid email address"]}
            )
        attrs["invite_data"] = invite_data
        return attrs


class MeetingInviteSerializer(BaseModelSerializer):
    """For update and read operations"""

    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "created_by",
            "last_modified_by",
            "meeting",
            "meeting_title",
            "modified",
            "pk",
            "state",
            "type",
            "used_at",
            "used_by",
        ]
        fields = read_only_fields + [
            "invite_data",
            "roles",
        ]

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title

    def validate_invite_data(self, value):
        reg = get_invite_data_registry()
        if self.instance.type not in reg:
            raise exceptions.ValidationError(
                f"Invite {self.instance.pk} has an invalid type: {self.instance.type}"
            )

        try:
            reg[self.instance.type](**{self.instance.type: value})
        except ValueError:
            raise exceptions.ValidationError(f"{value} is not a valid email address")
        return value.lower()


class ExternalMeetingInviteSerializer(serializers.ModelSerializer):
    """Used when querying from login service."""

    organisation_host = serializers.SerializerMethodField()
    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "created_by",
            "invite_data",
            "last_modified_by",
            "meeting",
            "meeting_title",
            "modified",
            "organisation_host",
            "pk",
            "roles",
            "state",
            "type",
            "used_at",
            "used_by",
        ]
        fields = read_only_fields

    def get_organisation_host(self, instance: MeetingInvite) -> str:
        try:
            return instance.meeting.organisation.host
        except AttributeError:
            # Only unittests!
            pass

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title
