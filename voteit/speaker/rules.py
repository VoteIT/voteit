import rules
from django.contrib.auth.models import User
from voteit.speaker.models import SpeakerListSystem


@rules.predicate
def is_list_moderator(user: User, list_system: SpeakerListSystem) -> bool:
    return (
        isinstance(list_system, SpeakerListSystem)
        and list_system.moderators.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_list_speaker(user: User, list_system: SpeakerListSystem) -> bool:
    return (
        isinstance(list_system, SpeakerListSystem)
        and list_system.speakers.filter(pk=user.pk).exists()
    )
