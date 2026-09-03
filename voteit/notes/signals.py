from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel

from voteit.core.decorators import on_transaction_commit
from voteit.notes.messages import NoteChanged
from voteit.notes.messages import NoteDeleted
from voteit.notes.collectors import note_payloads
from voteit.notes.models import Note


@receiver(post_save, sender=Note)
@on_transaction_commit
def _send_created_updated(*, instance: Note, **kwargs):
    ch = UserChannel(instance.user_id)
    # Same builder as the collector, so this push and a subscriber's initial
    # state cannot describe a note differently. One query either way: the dict
    # this replaced had to load instance.proposal for agenda_item_id. Looping
    # over the one row rather than .first() -- a note deleted later in the same
    # transaction sent note.deleted from pre_delete and needs nothing here.
    for data in note_payloads(Note.objects.filter(pk=instance.pk)):
        ch.sync_publish(NoteChanged(payload=data))


@receiver(pre_delete, sender=Note)
def _send_deleted(*, instance: Note, **kwargs):
    ch = UserChannel(instance.user_id)
    msg = NoteDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)
