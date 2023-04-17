from logging import getLogger

from rest_framework import serializers

from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.core.rest_api.serializers import BaseModelSerializer


logger = getLogger(__name__)


class InviteQuerySerializer(serializers.Serializer):
    scope = serializers.CharField()
    data = serializers.CharField()
    validated = serializers.DateTimeField()

    def validate_scope(self, value):
        if value not in get_invite_adapter_registry():
            logger.warning(f"No invite scope {value}")
        return value


class MeetingInviteSerializer(BaseModelSerializer):
    """
    For read operations
    """

    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "meeting",
            "meeting_title",
            "modified",
            "pk",
            "state",
            "used_at",
            "used_by",
            "user_data",
            "roles",
        ]
        fields = read_only_fields

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title


class ExternalMeetingInviteSerializer(serializers.ModelSerializer):
    """Used when querying from login service."""

    organisation_host = serializers.SerializerMethodField()
    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "user_data",
            "meeting",
            "meeting_title",
            "modified",
            "organisation_host",
            "pk",
            "roles",
            "state",
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
