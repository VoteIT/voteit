from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel

from voteit.core.decorators import on_transaction_commit
from voteit.notes.messages import NoteChanged
from voteit.notes.messages import NoteDeleted
from voteit.notes.models import Note


@receiver(post_save, sender=Note)
@on_transaction_commit
def _send_created_updated(*, instance: Note, **kwargs):
    ch = UserChannel(instance.user_id)
    data = {
        "pk": instance.pk,
        "proposal": instance.proposal_id,
        "agenda_item": instance.proposal.agenda_item_id,
        "meeting": instance.meeting_id,
        "user": instance.user_id,
        "body": instance.body,
        "intent": instance.intent,
        "created": instance.created,
    }
    ch.sync_publish(NoteChanged(payload=data))


@receiver(pre_delete, sender=Note)
def _send_deleted(*, instance: Note, **kwargs):
    ch = UserChannel(instance.user_id)
    msg = NoteDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)
