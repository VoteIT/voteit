from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.agenda import AgendaUpdated, AgendaDeleted
from voteit.messaging.registries import channel_registry


logger = getLogger(__name__)


@channel_registry("meeting")
class MeetingChannel(AbstractObjectChannel):
    """ This contains generic messages for the meeting. Agenda updates etc.
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
def agenda_change(instance=None, **kw):
    print(instance)  # FIXME Remove
    channel = MeetingChannel.from_instance(instance.meeting)
    msg = AgendaUpdated(items=[AgendaItemSerializer(instance).data])
    channel.sync_publish(msg)


@receiver(post_delete, sender=AgendaItem)
def agenda_delete(instance=None, **kw):
    channel = MeetingChannel.from_instance(instance.meeting)
    msg = AgendaDeleted(items=[AgendaItemSerializer(instance).data])
    channel.sync_publish(msg)
