from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.agenda import AgendaDeleted, AgendaAdded, AgendaChanged
from voteit.messaging.messages.poll import PollAdded, PollChanged, PollDeleted
from voteit.messaging.registries import channel_registry
from voteit.poll.models import Poll
from voteit.poll.rest_api.serializers import PollDetailSerializer

logger = getLogger(__name__)


@channel_registry("meeting")
class MeetingChannel(AbstractObjectChannel):
    """ This contains generic messages for the meeting.

        Transport for
        - Polls
        - Agenda (The title and order of agenda items)
        - Anything public related to the meeting
    """
    logger = logger
    Model = Meeting

    @property
    def channel_name(self) -> str:
        """ Return name of this channel based on the primary key of an object"""
        return f"meeting_{self.pk}"

    def allow_subscribe(self, user):
        instance = self.get_instance()
        return user.has_perm(MeetingPermissions.VIEW, instance)


@channel_registry("moderator")
class ModeratorChannel(AbstractObjectChannel):
    """ Moderator specific messages

        Transport for:
        - private agenda items
        - Updates for things that only moderators need to know (The number of present users for instance)
    """
    logger = logger
    Model = Meeting

    @property
    def channel_name(self) -> str:
        """ Return name of this channel based on the primary key of an object"""
        return f"moderator_{self.pk}"

    def allow_subscribe(self, user):
        instance = self.get_instance()
        return user.has_perm(MeetingPermissions.MODERATE, instance)


# FIXME: Split updates on state change for moderators or regular users. Essentially an instance made private

@receiver(post_save, sender=AgendaItem)
def agenda_change(instance=None, created=None, **kw):
    print(instance)  # FIXME Remove
    channel = MeetingChannel.from_instance(instance.meeting)
    data = AgendaItemSerializer(instance).data
    if created:
        msg = AgendaAdded(item=data)
    else:
        msg = AgendaChanged(item=data)
    channel.sync_publish(msg)


@receiver(post_delete, sender=AgendaItem)
def agenda_delete(instance=None, **kw):
    channel = MeetingChannel.from_instance(instance.meeting)
    # FIXME: Create a serializer that only sends primary keys?
    msg = AgendaDeleted(pk=instance.pk)
    channel.sync_publish(msg)


@receiver(post_save, sender=Poll)
def poll_change(instance=None, created=None, **kw):
    if instance.meeting is not None:
        channel = MeetingChannel.from_instance(instance.meeting)
        data = PollDetailSerializer(instance).data
        if created:
            msg = PollAdded(item=data)
        else:
            msg = PollChanged(item=data)
        channel.sync_publish(msg)


@receiver(post_delete, sender=Poll)
def poll_delete(instance=None, **kw):
    if instance.meeting is not None:
        channel = MeetingChannel.from_instance(instance.meeting)
        msg = PollDeleted(pk=instance.pk)
        channel.sync_publish(msg)
