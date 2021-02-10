from rest_framework import serializers
from typing import List

from voteit.access_policy.app.policies import ModeratorApprovedAccess, AutomaticAccess
from voteit.access_policy.utils import get_policies
from voteit.meeting.models import Meeting


class AutomaticAccessSerializer(serializers.ModelSerializer):
    """
    >>> from voteit.meeting.models import Meeting
    >>> meeting = Meeting.objects.create()
    >>> ap = AutomaticAccess.objects.create(meeting=meeting, active=True, roles_given=["participant"])
    >>> data = AutomaticAccessSerializer(ap).data
    >>> data["pk"] == ap.pk
    True
    >>> data["name"] == AutomaticAccess.name
    True
    """

    class Meta:
        model = AutomaticAccess
        fields = "pk", "meeting", "active", "name", "roles_given"


class ModeratorApprovedAccessSerializer(serializers.ModelSerializer):
    """
    >>> from voteit.meeting.models import Meeting
    >>> meeting = Meeting.objects.create()
    >>> ap = ModeratorApprovedAccess.objects.create(meeting=meeting, active=True)
    >>> data = ModeratorApprovedAccessSerializer(ap).data
    >>> data["pk"] == ap.pk
    True
    >>> data["name"] == ModeratorApprovedAccess.name
    True
    """

    class Meta:
        model = ModeratorApprovedAccess
        fields = "pk", "meeting", "active", "name"


ap_to_serializer = {
    ModeratorApprovedAccess.name: ModeratorApprovedAccessSerializer,
    AutomaticAccess.name: AutomaticAccessSerializer,
}


class MeetingAccessPoliciesSerializer(serializers.ModelSerializer):
    """
    Return serialized version of policies for a specific meeting
    >>> from voteit.meeting.models import Meeting
    >>> meeting = Meeting.objects.create()
    >>> ap = AutomaticAccess.objects.create(meeting=meeting, active=True, roles_given=["participant"])
    >>> data = MeetingAccessPoliciesSerializer(meeting).data
    >>> data["pk"] == meeting.pk
    True

    >>> len(data["policies"])
    1
    """

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
