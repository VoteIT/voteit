from __future__ import annotations


from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver


from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import AgendaBodyChanged
from voteit.agenda.messages import AgendaBodyDeleted
from voteit.agenda.messages import AgendaDeleted
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemBodySerializer
from voteit.agenda.rest_api.serializers import AgendaItemListSerializer
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.abcs import AgendaItemContext
from voteit.core.decorators import disable_on_raw_save
from voteit.discussion.models import DiscussionPost
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.core.signals import after_sm_transition
from voteit.meeting.signals import archive_meeting
from voteit.proposal.models import Proposal


@receiver(post_save, sender=AgendaItem)
@disable_on_raw_save
def agenda_change(instance: AgendaItem = None, **kw):
    participants_ch = ParticipantsChannel.from_instance(instance.meeting)
    moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
    data = AgendaItemListSerializer(instance).data
    # Base message that might only get sent to moderators
    msg = AgendaChanged(payload=data)
    if not instance.is_private:
        # The agenda item isn't private so publish to everyone
        participants_ch.sync_publish(msg)
    moderators_ch.sync_publish(msg)
    # And body for AI channel
    ai_ch = AgendaItemChannel.from_instance(instance)
    data = AgendaItemBodySerializer(instance).data
    ai_ch.sync_publish(AgendaBodyChanged(payload=data))


@receiver(after_sm_transition, sender=AgendaItem)
def ai_made_private(instance: AgendaItem, source, target, event, **kw):
    """
    Set as deleted for participants.
    Body won't receive a message so cleanup has to be handled differently.
    """
    if (
        target.value == AgendaItemStateMachine.private.value
        and instance.meeting is not None
    ):
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        msg_deleted = AgendaDeleted(payload={"pk": instance.pk})
        participants_ch.sync_publish(msg_deleted)


@receiver(pre_delete, sender=AgendaItem)
def agenda_delete(instance: AgendaItem = None, **kw):
    if instance.meeting:
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        msg = AgendaDeleted(payload={"pk": instance.pk})
        meeting_ch.sync_publish(msg)
        # We can send this to meeting too, it might not exist though
        msg = AgendaBodyDeleted(payload={"pk": instance.pk})
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
            instance.agenda_item.refresh_from_db(fields=["state", "related_modified"])
        except AgendaItem.DoesNotExist:  # pragma: no cover
            return
        instance.agenda_item.revert_to_last_related_modified()
