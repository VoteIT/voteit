from itertools import groupby

from django.db import models
from django.dispatch import receiver

from voteit.core.workflows import EnabledWf
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.models import ParticipantTags
from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema, Priority
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.registries import list_method
from voteit.speaker.signals import list_method_added
from voteit.speaker.signals import list_method_removed


class GenderAndPrioritySchema(PrioritySettingsSchema):
    priority_genders: list[str] = ["f", "nb"]

    class Config:
        allow_mutation = False


@list_method
class GenderAndPriority(Priority):
    name = "gender_prio"
    title = "Gender and priority"
    description = (
        "Users who've spoken less than others in the queue will be prioritised. "
        "At least every second speaker from prioritized genders within same group."
    )
    settings_schema = GenderAndPrioritySchema

    def reorder(self, safe_speakers, incoming_order):
        priority_genders = self.speaker_system.settings.priority_genders

        def is_prio(sp: Speaker):
            return sp.gender_tag in priority_genders

        should_prioritize = bool(safe_speakers) and not is_prio(safe_speakers[-1])
        spoken_count_order = super().reorder(safe_speakers, incoming_order)
        # Go through each list and yield in prio order
        for _, speakers in groupby(spoken_count_order, lambda sp: sp.spoken_count):
            speakers = list(speakers)
            while speakers:
                # Preliminary choice is next speaker in list
                speaker = speakers[0]
                if should_prioritize:
                    # See if there is a speaker to prioritize
                    speaker = next(filter(is_prio, speakers), speaker)
                # Whether next should be prioritized (i.e. if this speaker is not prioritized gender)
                should_prioritize = not is_prio(speaker)
                # Remove and yield
                speakers.remove(speaker)
                yield speaker

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


@receiver(sender=GenderAndPriority, signal=list_method_added)
def check_component_on_enable(instance: SpeakerListSystem, **kwargs):
    component, _ = instance.meeting.components.update_or_create(
        component_name=GenderTags.name,
        defaults={"settings_data": {"tags": ["m", "f", "nb"]}, "state": EnabledWf.ON},
    )
    assert component.is_valid


@receiver(sender=GenderAndPriority, signal=list_method_removed)
def maybe_remove_component_on_disable(instance: SpeakerListSystem, **kwargs):
    # TODO: This needs to be handled differently in case this component is reused later on.
    # Remove component if no other speaker lists use it
    if (
        not instance.meeting.speaker_systems.exclude(pk=instance.pk)
        .filter(method_name=GenderAndPriority.name)
        .exists()
    ):
        if component := instance.meeting.components.filter(
            component_name=GenderTags.name, state=EnabledWf.ON
        ).first():
            component.disable()
            component.save()
