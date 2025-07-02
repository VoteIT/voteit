from contextlib import suppress

from django.db import models

from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.models import ParticipantTags
from voteit.speaker.abcs import ListMethod
from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.registries import list_method


class GenderAndPrioritySchema(PrioritySettingsSchema):
    priority_genders: list[str]

    class Config:
        allow_mutation = False


@list_method
class GenderAndPriority(ListMethod):
    name = "gender_prio"
    title = "Gender and priority"
    description = (
        "Users who've spoken less than others in the queue will be prioritised. "
        "At least every second speaker from prioritized genders within same group."
    )
    settings_schema = GenderAndPrioritySchema

    def reorder(self, safe_speakers, incoming_order):
        max_priority = self.speaker_system.settings.max_times or 1_000_000
        priority_genders = self.speaker_system.settings.priority_genders

        def order_key(speaker: Speaker) -> tuple[int, int]:
            return (
                min(speaker.spoken_count, max_priority),
                incoming_order.index(speaker),
            )

        initially_sorted = sorted(incoming_order, key=order_key)

        # See if any of the speakers should pass within their ordering
        new_order = []

        while initially_sorted:
            speaker = initially_sorted.pop(0)
            insert_pos = len(new_order)
            curr_spoken_cmp = min(speaker.spoken_count, max_priority)
            while insert_pos:
                previous = new_order[insert_pos - 1]
                # if previous in safe_speakers:
                #    break
                # Break if previous user has spoken less
                previous_spoken_cmp = min(previous.spoken_count, max_priority)
                if curr_spoken_cmp > previous_spoken_cmp:
                    break
                if curr_spoken_cmp < previous_spoken_cmp:  # pragma: no cover
                    raise Exception("Something went wrong with sorting?")
                if curr_spoken_cmp == previous_spoken_cmp:
                    if speaker.gender_tag not in priority_genders:
                        break
                    if previous.gender_tag in priority_genders:
                        break
                    # And the one before the previous one...
                    earlier = None
                    with suppress(IndexError):
                        earlier = new_order[insert_pos - 2]
                    if earlier is None:
                        with suppress(IndexError):
                            earlier = safe_speakers[-1]
                    if (
                        not earlier
                        or earlier.gender_tag in priority_genders
                        or earlier in safe_speakers
                    ):
                        break

                insert_pos -= 1

            new_order.insert(insert_pos, speaker)
        return new_order

    def get_queryset(self, speaker_list: SpeakerList) -> models.QuerySet[Speaker]:
        return speaker_list.speakers_in_queue_or_speaking().annotate(
            spoken_count=Speaker.objects.filter(
                speaker_list=speaker_list,
                seconds__isnull=False,
                user=models.OuterRef("user"),
            )
            .annotate(count=models.Func(models.F("id"), function="Count"))
            .values("count"),
            gender_tag=ParticipantTags.objects.filter(
                meeting_id=speaker_list.meeting_id, user=models.OuterRef("user")
            ).values(f"tags__{GenderTags.namespace}"),
        )
