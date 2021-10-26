from typing import List

from pydantic import ValidationError
from rest_framework import serializers
from rest_framework import exceptions

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.app.policies import ModeratorApprovedAccess
from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.utils import get_invite_data_registry
from voteit.access_policy.utils import get_policies
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.meeting.models import Meeting


class AutomaticAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomaticAccess
        fields = "pk", "meeting", "active", "name", "roles_given"


class ModeratorApprovedAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModeratorApprovedAccess
        fields = "pk", "meeting", "active", "name"


ap_to_serializer = {
    ModeratorApprovedAccess.name: ModeratorApprovedAccessSerializer,
    AutomaticAccess.name: AutomaticAccessSerializer,
}


class MeetingAccessPoliciesSerializer(serializers.ModelSerializer):

    policies = serializers.SerializerMethodField("get_enabled_policies")

    class Meta:
        model = Meeting
        fields = "pk", "policies"

    def get_enabled_policies(self, meeting) -> List:
        result = []
        for ap in get_policies(meeting):
            serializer = ap_to_serializer[ap.name]
            result.append(serializer(ap).data)
        return result


class InviteQuerySerializer(serializers.Serializer):
    scope = serializers.CharField()
    data = serializers.CharField()
    validated = serializers.DateTimeField()

    # FIXME: Validate scope, data and validated


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
            "roles",
            "meeting",
        ]

    def validate_invite_data(self, value):
        reg = get_invite_data_registry()
        try:
            reg.validate(value)
        except ValidationError as exc:
            raise exceptions.ValidationError(str(exc))
        except ValueError as exc:
            raise exceptions.ValidationError("Invalid keys within data")
        return value


class MeetingInviteSerializer(CreateMeetingInviteSerializer):
    """For update and read operations"""

    meeting_title = serializers.SerializerMethodField()

    class Meta(CreateMeetingInviteSerializer.Meta):
        read_only_fields = [
            "created",
            "created_by",
            "last_modified_by",
            "last_sent",
            "matched",
            "meeting",
            "modified",
            "pk",
            "send_state",
            "state",
            "used_at",
            "used_by",
            "meeting_title",
        ]
        fields = read_only_fields + [
            "invite_data",
            "roles",
        ]

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title


class ExternalMeetingInviteSerializer(serializers.ModelSerializer):
    """Used when querying from login service."""

    organisation_pk = serializers.SerializerMethodField()
    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "created_by",
            "invite_data",
            "last_modified_by",
            "last_sent",
            "matched",
            "meeting",
            "meeting_title",
            "modified",
            "organisation_pk",
            "pk",
            "roles",
            "send_state",
            "state",
            "used_at",
            "used_by",
        ]
        fields = read_only_fields

    def get_organisation_pk(self, instance: MeetingInvite) -> int:
        try:
            return instance.meeting.organisation.pk
        except AttributeError:
            # Only unittests!
            pass

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title
