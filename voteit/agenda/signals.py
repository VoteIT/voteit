from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.messages import AgendaAdded
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import AgendaDeleted
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.signals import archive_meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """ Send agenda items to client. """
    # TODO Filter based on user permissions (client handle if showing private ai:s for now)
    app_state.append_from_queryset(
        context.agenda_items.all(), AgendaItemSerializer, AgendaAdded
    )


# FIXME: Split updates on state change for moderators or regular users. Essentially an instance made private


@receiver(post_save, sender=AgendaItem)
def agenda_change(instance=None, created=None, **kw):
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
    msg = AgendaDeleted({}, pk=instance.pk)
    ch.publish(msg)


@receiver(archive_meeting)
def archive_agenda_items(meeting: Meeting, **kw):
    for ai in meeting.agenda_items.all():
        ai.archive()
        ai.save()
