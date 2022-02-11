from rest_framework import serializers

from voteit.bug_reports.models import BugReport
from voteit.core.loggers import slack_logger
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
        slack_logger.info(
            f"Bug report in {meeting.organisation.title}/{meeting.title}:\n{validated_data['description']}"
        )
        return super().create({
            **validated_data,
            'user': user,
            'user_roles': tuple(meeting.get_roles(user))          # Roles at time of bug report
        })
