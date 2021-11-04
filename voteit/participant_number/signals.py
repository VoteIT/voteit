from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.core.decorators import receiver_all_subclasses
from voteit.meeting.channels import ModeratorsChannel
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.participant_number.messages import PNAdded
from voteit.participant_number.messages import PNChanged
from voteit.participant_number.messages import PNDeleted
from voteit.participant_number.models import ParticipantNumber

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Populate app_state with participant numbers
    """
    with suppress(ObjectDoesNotExist):
        for item in context.pn_system.numbers.all().values(
            "number",
            "user",
            "pk",
        ):
            app_state.append(
                PNAdded(meeting=context.pk, **item)
            )


@receiver_all_subclasses(post_save, sender=ParticipantNumber)
def pn_updated(instance: ParticipantNumber = None, created=None, **kw):
    if instance.pns.meeting is None:
        return
    moderators_ch = ModeratorsChannel.from_instance(instance.pns.meeting)
    msg_klass = created and PNAdded or PNChanged
    msg = msg_klass(
        meeting=instance.pns.meeting.pk,
        number=instance.number,
        user=instance.user.pk,
        pk=instance.pk,
    )
    moderators_ch.publish(msg)


@receiver_all_subclasses(pre_delete, sender=ParticipantNumber)
def pn_deleted(instance: ParticipantNumber = None, **kw):
    if instance.pns.meeting is None:
        return
    moderators_ch = ModeratorsChannel.from_instance(instance.pns.meeting)
    msg = PNDeleted(
        pk=instance.pk,
    )
    moderators_ch.publish(msg)
