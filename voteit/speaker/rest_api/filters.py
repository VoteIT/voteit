from django_filters import rest_framework as filters

from voteit.meeting.models import Meeting
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem


def users_speaker_systems_qs(request):
    return SpeakerListSystem.objects.filter(meeting__participants=request.user)


def users_meetings(request):
    return Meeting.objects.filter(participants=request.user)


class SpeakerFilterSet(filters.FilterSet):
    speaker_system = filters.ModelChoiceFilter(
        queryset=users_speaker_systems_qs,
        required=False,
        field_name="speaker_list__speaker_system",
    )
    meeting = filters.ModelChoiceFilter(
        queryset=users_meetings,
        required=True,
        field_name="speaker_list__meeting",
    )

    class Meta:
        model = Speaker
        fields = ()
