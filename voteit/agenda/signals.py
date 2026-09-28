from __future__ import annotations


from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.db.transaction import get_connection
from django.dispatch import receiver


from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import AgendaBodyChanged
from voteit.agenda.messages import AgendaDeleted
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import AgendaItemBodySerializer
from voteit.agenda.rest_api.serializers import AgendaItemListSerializer
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.abcs import AgendaItemContext
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.discussion.models import DiscussionPost
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.core.signals import after_sm_transition
from voteit.meeting.signals import archive_meeting
from voteit.proposal.models import Proposal


def publish_agenda_changed(instance: AgendaItem, on_commit: bool = True):
    msg = AgendaChanged(payload=AgendaItemListSerializer(instance).data)
    if not instance.is_private:
        ParticipantsChannel(instance.meeting_id).sync_publish(msg, on_commit=on_commit)
    ModeratorsChannel(instance.meeting_id).sync_publish(msg, on_commit=on_commit)


@receiver(post_save, sender=AgendaItem)
@disable_on_raw_save
def agenda_change(instance: AgendaItem = None, **kw):
    publish_agenda_changed(instance)
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
        msg = AgendaDeleted(payload={"pk": instance.pk})
        broadcast_meeting(instance.meeting, msg)


@receiver(archive_meeting)
def archive_agenda_items(meeting: Meeting, **kw):
    for ai in meeting.agenda_items.all():
        ai.archive()
        ai.save()


class RelatedModifiedPush:
    """Pushes each agenda item whose related_modified may have changed, once, after commit.

    Items deleted in the same transaction (a cascade) are simply not found.
    """

    def __init__(self) -> None:
        self.pks: set[int] = set()

    def __call__(self) -> None:
        for ai in AgendaItem.objects.filter(pk__in=self.pks).with_related_modified():
            # Already committed, batching would only defer it again
            publish_agenda_changed(ai, on_commit=False)


def schedule_related_modified_push(ai_pk: int) -> None:
    """Same lookup as messaging.utils._get_or_create_batcher, so a rollback drops the push."""
    conn = get_connection()
    for entry in conn.run_on_commit:
        if isinstance(entry[1], RelatedModifiedPush):
            entry[1].pks.add(ai_pk)
            return
    push = RelatedModifiedPush()
    push.pks.add(ai_pk)
    # Runs right away outside of atomic blocks
    conn.on_commit(push)


@receiver(post_save, sender=DiscussionPost)
@receiver_all_subclasses(post_save, sender=Proposal)
@disable_on_raw_save
def content_created(instance: AgendaItemContext, created=None, **kwargs):
    if created and instance.agenda_item_id is not None:
        schedule_related_modified_push(instance.agenda_item_id)


@receiver(post_delete, sender=DiscussionPost)
@receiver_all_subclasses(post_delete, sender=Proposal)
def content_deleted(instance: AgendaItemContext, **kwargs):
    if instance.agenda_item_id is not None:
        schedule_related_modified_push(instance.agenda_item_id)
