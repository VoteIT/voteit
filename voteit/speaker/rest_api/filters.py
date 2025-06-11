from django_filters import rest_framework as filters

from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem


def users_speaker_systems_qs(request):
    return SpeakerListSystem.objects.filter(meeting__roles__user=request.user)


class SpeakerFilterSet(filters.FilterSet):
    speaker_system = filters.ModelChoiceFilter(
        queryset=users_speaker_systems_qs,
        required=True,
        field_name="speaker_list__speaker_system",
    )

    class Meta:
        model = Speaker
        fields = ()
