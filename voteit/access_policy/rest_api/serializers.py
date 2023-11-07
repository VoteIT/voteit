from rest_framework import serializers

# from voteit.access_policy.app.policies import ModeratorApprovedAccess
from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.utils import get_policies
from voteit.core.rest_api.fields import RolesField
from voteit.meeting.models import Meeting


class CreateAutomaticAccessSerializer(serializers.ModelSerializer):
    roles_given = RolesField()

    class Meta:
        model = AutomaticAccess
        fields = (
            "pk",
            "meeting",
            "active",
            "name",
            "roles_given",
        )


class AutomaticAccessSerializer(CreateAutomaticAccessSerializer):
    class Meta(CreateAutomaticAccessSerializer.Meta):
        read_only_fields = ("meeting",)


# class ModeratorApprovedAccessSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = ModeratorApprovedAccess
#         fields = "pk", "meeting", "active", "name"


ap_to_serializer = {
    # ModeratorApprovedAccess.name: ModeratorApprovedAccessSerializer,
    AutomaticAccess.name: AutomaticAccessSerializer,
}


class MeetingAccessPoliciesSerializer(serializers.ModelSerializer):
    policies = serializers.SerializerMethodField("get_enabled_policies")

    class Meta:
        model = Meeting
        fields = "pk", "policies"

    def get_enabled_policies(self, meeting) -> list:
        result = []
        for ap in get_policies(meeting, only_active=False):
            serializer = ap_to_serializer[ap.name]
            result.append(serializer(ap).data)
        return result
