from typing import List

from rest_framework import serializers

from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem


class SpeakerListSerializer(serializers.ModelSerializer):
    # FIXME: Don't allow system and agenda items to be within different meetings
    # It's at least prevented in .save() right now
    class Meta:
        model = SpeakerList
        read_only_fields = [
            "state",
        ]
        fields = [
            "pk",
            "title",
            "list_system",
            "agenda_item",
        ] + read_only_fields
        extra_kwargs = {
            # At least right now...
            "agenda_item": {"required": True},
            "meeting": {"required": True},
        }


class HistoricSpeakerListSerializer(serializers.ModelSerializer):
    previous = serializers.SerializerMethodField("get_previous")

    class Meta:
        model = SpeakerList
        fields = ("pk", "previous")
        read_only_fields = fields

    def get_previous(self, speaker_list: SpeakerList) -> List[List]:
        """Return historic speaker lists. Each item in the list is a tuple where userid is the
        first value and then a list with the number of seconds they spoke for each entry.

        A user with userid 1 that has spoken 10 seconds the first time and 20 seconds
        the last time would look like this:

        [[1, [10, 20],]
        """
        instance: SpeakerList = self.instance
        # FIXME optimize query
        results = []
        for user_pk in list(
            instance.speaker_items.values_list("user", flat=True).distinct()
        ):
            seconds = list(
                instance.speaker_items.filter(seconds__isnull=False, user=user_pk)
                .order_by("started")
                .values_list("seconds", flat=True)
            )
            if seconds:
                results.append([user_pk, seconds])
        return results


class SpeakerListSystemSerializer(serializers.ModelSerializer):
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = SpeakerListSystem
        read_only_fields = ["archived"]
        fields = [
            "pk",
            "meeting",
            "method_name",
            "title",
            "settings",
            "active_list",
            "safe_positions",
            "active",
        ] + read_only_fields
        extra_kwargs = {
            # At least right now...
            "meeting": {"required": True},
        }
