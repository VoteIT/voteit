from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.meeting.channels import MeetingChannel
from voteit.participant_number.messages import PNChanged
from voteit.participant_number.messages import PNDeleted
from voteit.participant_number.models import ParticipantNumber


logger = getLogger(__name__)


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
