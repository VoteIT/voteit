from typing import List

from pydantic import ValidationError
from rest_framework import serializers

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


class MeetingInviteSerializer(BaseModelSerializer):
    author_kw = "created_by"

    class Meta:
        model = MeetingInvite
        # FIXME: Readonly etc
        fields = ["pk"] + [f.name for f in MeetingInvite._meta.get_fields()]
        read_only_fields = ["created_by"]  # Forced via BaseModelSerailizer

    def validate_data(self, value):
        reg = get_invite_data_registry()
        try:
            reg.validate(value)
        except ValidationError as exc:
            raise serializers.ValidationError(str(exc))
        except ValueError as exc:
            raise serializers.ValidationError("Invalid keys within data")
        return value
