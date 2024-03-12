from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_fsm import post_transition

from envelope.messages.common import Batch
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.messages import AgendaAdded
from voteit.agenda.messages import AgendaBodyAdded
from voteit.agenda.messages import AgendaBodyChanged
from voteit.agenda.messages import AgendaBodyDeleted
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import AgendaDeleted
from voteit.agenda.messages import LastReadChanged
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemBodySerializer
from voteit.agenda.rest_api.serializers import AgendaItemListSerializer
from voteit.agenda.rest_api.serializers import LastReadSerializer
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.abcs import AgendaItemContext
from voteit.core.decorators import disable_on_raw_save
from voteit.discussion.models import DiscussionPost
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.signals import archive_meeting
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db import models
    from envelope.channels.models import AppState


def _attach_agenda_items(qs: models.QuerySet[AgendaItem], app_state: AppState):
    serializer = AgendaItemListSerializer(qs, many=True)
    if serializer.data:
        batch = Batch(t=AgendaAdded.name, payloads=[])
        for item in serializer.data:
            batch.append(AgendaAdded(data=item))
        app_state.append(batch)


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send non-private agenda items to regular users.
    """
    _attach_agenda_items(
        context.agenda_items.exclude(state=AgendaItemWf.PRIVATE), app_state
    )


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send all agenda items
    """
    _attach_agenda_items(context.agenda_items.all(), app_state)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    # This will cause last read to be sent for private agenda items that the user has visited,
    # but that shouldn't be a problem.
    serializer = LastReadSerializer(context.last_read_set.filter(user=user), many=True)
    if serializer.data:
        batch = Batch(t=LastReadChanged.name, payloads=[])
        for item in serializer.data:
            batch.append(LastReadChanged(data=item))
        app_state.append(batch)


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """
    Send full AI info
    """
    msg = AgendaBodyAdded(**AgendaItemBodySerializer(context).data)
    app_state.append(msg)


@receiver(post_save, sender=AgendaItem)
@disable_on_raw_save
def agenda_change(instance: AgendaItem = None, created=None, **kw):
    participants_ch = ParticipantsChannel.from_instance(instance.meeting)
    moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
    data = AgendaItemListSerializer(instance).data
    # Base message that might only get sent to moderators
    if created:
        msg = AgendaAdded(data=data)
    else:
        msg = AgendaChanged(data=data)
    if not instance.is_private:
        # The agenda item isn't private so publish to everyone
        participants_ch.sync_publish(msg)
    moderators_ch.sync_publish(msg)
    # And body for AI channel
    ai_ch = AgendaItemChannel.from_instance(instance)
    data = AgendaItemBodySerializer(instance).data
    if created:
        msg = AgendaBodyAdded(data=data)
    else:
        msg = AgendaBodyChanged(data=data)
    ai_ch.sync_publish(msg)


@receiver(post_transition, sender=AgendaItem)
def ai_made_private(instance: AgendaItem, source: str, target: str, **kw):
    """
    Set as deleted for participants.
    Body won't receive a message so cleanup has to be handled differently.
    """
    if target == AgendaItemWf.PRIVATE and instance.meeting is not None:
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        msg_deleted = AgendaDeleted(pk=instance.pk)
        participants_ch.sync_publish(msg_deleted)


@receiver(pre_delete, sender=AgendaItem)
def agenda_delete(instance: AgendaItem = None, **kw):
    if instance.meeting:
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        msg = AgendaDeleted(pk=instance.pk)
        meeting_ch.sync_publish(msg)
        # We can send this to meeting too, it might not exist though
        msg = AgendaBodyDeleted(pk=instance.pk)
        meeting_ch.sync_publish(msg)


@receiver(archive_meeting)
def archive_agenda_items(meeting: Meeting, **kw):
    for ai in meeting.agenda_items.all():
        ai.archive()
        ai.save()


@receiver(post_save, sender=DiscussionPost)
@receiver(post_save, sender=Proposal)
@disable_on_raw_save
def mark_ai_as_updated(instance: AgendaItemContext, created=None, **kwargs):
    if created and instance.agenda_item is not None:
        instance.agenda_item.maybe_mark_related_modified()


@receiver(post_delete, sender=DiscussionPost)
@receiver(post_delete, sender=Proposal)
def revert_to_last_updated(instance: AgendaItemContext, **kwargs):
    if instance.agenda_item is not None:
        try:
            instance.agenda_item.refresh_from_db(fields=["pk"])
        except AgendaItem.DoesNotExist:  # pragma: no cover
            return
        instance.agenda_item.revert_to_last_related_modified()
