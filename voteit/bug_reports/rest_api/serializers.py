from rest_framework import serializers

from voteit.bug_reports.models import BugReport
from voteit.meeting.models import Meeting


class BugReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BugReport
        read_only_fields = ("pk", "user", "user_roles")
        fields = read_only_fields + (
            "meeting",
            "user_platform",
            "function",
            "description",
        )

    def create(self, validated_data):
        user = self.context['request'].user
        meeting: Meeting = validated_data['meeting']
        return super().create({
            **validated_data,
            'user': user,
            'user_roles': meeting.get_roles(user)
        })
