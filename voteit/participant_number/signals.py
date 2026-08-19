from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.meeting.channels import MeetingChannel
from voteit.participant_number.messages import PNChanged
from voteit.participant_number.messages import PNDeleted
from voteit.participant_number.models import ParticipantNumber

if TYPE_CHECKING:
    from voteit.messaging.state import AppState
    from voteit.meeting.models import Meeting


logger = getLogger(__name__)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Populate app_state with participant numbers
    """
    try:
        pn_system = context.pn_system
    except ObjectDoesNotExist:
        return
    for item in pn_system.numbers.all().values(
        "number",
        "user",
        "pk",
    ):
        app_state.append(PNChanged(payload={"meeting": context.pk, **item}))


@receiver_all_subclasses(post_save, sender=ParticipantNumber)
@disable_on_raw_save
def pn_updated(instance: ParticipantNumber = None, **kw):
    if instance.pns.meeting is None:
        return
    channel = MeetingChannel.from_instance(instance.pns.meeting)
    msg = PNChanged(
        payload={
            "meeting": instance.pns.meeting.pk,
            "number": instance.number,
            "user": instance.user.pk,
            "pk": instance.pk,
        }
    )
    channel.sync_publish(msg)


@receiver_all_subclasses(pre_delete, sender=ParticipantNumber)
def pn_deleted(instance: ParticipantNumber = None, **kw):
    if instance.pns.meeting is None:
        return
    channel = MeetingChannel.from_instance(instance.pns.meeting)
    msg = PNDeleted(payload={"pk": instance.pk})
    channel.sync_publish(msg)
