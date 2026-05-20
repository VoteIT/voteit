from django.contrib.auth import get_user_model
from rest_framework import serializers

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting

User = get_user_model()


class ViewableMeetingField(serializers.PrimaryKeyRelatedField):
    """
    The current user can see that the meeting exist. Takes care of
    """

    def get_queryset(self):
        return Meeting.objects.for_user(self.context["request"].user)


class ParticipantMeetingField(serializers.PrimaryKeyRelatedField):
    """
    The current user is a participant in the specified meeting.
    """

    def get_queryset(self):
        return Meeting.objects.filter(participants=self.context["request"].user)


class UserInSameMeetingsField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return User.objects.filter(
            meeting_roles__context__in=Meeting.objects.filter(
                roles__user=self.context["request"].user
            )
        ).distinct()


class UserInMeetingContextField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        if not isinstance(self.root.instance, MeetingContext):
            raise TypeError("Instance must implement MeetingContext")
        meeting = self.root.instance.meeting
        return meeting.participants.all()
