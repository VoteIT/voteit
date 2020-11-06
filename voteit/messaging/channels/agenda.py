from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.agenda import AgendaUpdated
from voteit.messaging.registries import channel_registry


logger = getLogger(__name__)


@channel_registry("agenda")
class AgendaChannel(AbstractObjectChannel):
    """ Note that this is the agenda, so it has meeting as a base. Not an agenda item!
    """
    logger = logger
    Model = Meeting

    @property
    def channel_name(self) -> str:
        """ Return name of this channel based on the primary key of an object"""
        return f"agenda_{self.pk}"

    def allow_subscribe(self, user):
        instance = self.get_instance()
        return user.has_perm(MeetingPermissions.VIEW, instance)


@receiver(post_save, sender=AgendaItem)
def agenda_change(instance=None, **kw):
    channel = AgendaChannel.from_instance(instance.meeting)
    msg = AgendaUpdated(items=[{"pk": instance.pk, "title": instance.title}])
    channel.sync_publish(msg)
