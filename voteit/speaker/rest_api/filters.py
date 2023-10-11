from django_filters import rest_framework as filters

from voteit.speaker.models import Speaker


class SpeakerFilterSet(filters.FilterSet):
    meeting = filters.NumberFilter(
        field_name="speaker_list__speaker_system__meeting", label="Meeting"
    )
    speaker_system = filters.NumberFilter(
        field_name="speaker_list__speaker_system", label="Speaker system"
    )

    class Meta:
        model = Speaker
        fields = ()
