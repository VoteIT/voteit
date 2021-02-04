from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.agenda.messages import AgendaDeleted, AgendaAdded, AgendaChanged
from voteit.messaging.decorators import channel
from voteit.poll.messages import PollAdded, PollChanged, PollDeleted
from voteit.poll.models import Poll
from voteit.poll.rest_api.serializers import PollDetailSerializer

logger = getLogger(__name__)


@channel
class MeetingChannel(AbstractObjectChannel):
    """ This contains generic messages for the meeting.

        Transport for
        - Polls
        - Agenda (The title and order of agenda items)
        - Anything public related to the meeting
    """
    name="meeting"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.VIEW


@channel
class ModeratorChannel(AbstractObjectChannel):
    """ Moderator specific messages

        Transport for:
        - private agenda items
        - Updates for things that only moderators need to know (The number of present users for instance)
    """
    name="moderator"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.MODERATE


@receiver(post_save, sender=Meeting)
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        ch = MeetingChannel.from_instance(instance)
        msg = MeetingChanged({}, **data)
        ch.publish(msg)

# FIXME: Split updates on state change for moderators or regular users. Essentially an instance made private

@receiver(post_save, sender=AgendaItem)
def agenda_change(instance=None, created=None, **kw):
    print(instance)  # FIXME Remove
    ch = MeetingChannel.from_instance(instance.meeting)
    data = AgendaItemSerializer(instance).data
    if created:
        msg = AgendaAdded({}, **data)
    else:
        msg = AgendaChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=AgendaItem)
def agenda_delete(instance=None, **kw):
    ch = MeetingChannel.from_instance(instance.meeting)
    # FIXME: Create a serializer that only sends primary keys?
    msg = AgendaDeleted({}, pk=instance.pk)
    ch.publish(msg)


@receiver(post_save, sender=Poll)
def poll_change(instance=None, created=None, **kw):
    if instance.meeting is not None:
        ch = MeetingChannel.from_instance(instance.meeting)
        data = PollDetailSerializer(instance).data
        if created:
            msg = PollAdded({}, **data)
        else:
            msg = PollChanged({}, **data)
        ch.publish(msg)


@receiver(pre_delete, sender=Poll)
def poll_delete(instance=None, **kw):
    if instance.meeting is not None:
        ch = MeetingChannel.from_instance(instance.meeting)
        msg = PollDeleted({}, pk=instance.pk)
        ch.publish(msg)
