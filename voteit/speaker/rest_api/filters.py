from django_filters import rest_framework as filters

from voteit.core.rest_api.filters import RequiredModelChoiceFilter
from voteit.meeting.models import Meeting
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


def users_speaker_systems_qs(request):
    return SpeakerListSystem.objects.filter(meeting__participants=request.user)


class SpeakerSystemRolesFilterSet(filters.FilterSet):
    context = RequiredModelChoiceFilter(
        queryset=users_speaker_systems_qs, label="Speaker system"
    )
    user_id_in = NumberInFilter(field_name="user_id", lookup_expr="in")

    class Meta:
        model = SpeakerSystemRoles
        fields = ("context", "user_id_in")


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
