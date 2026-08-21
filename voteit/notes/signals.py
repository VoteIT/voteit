from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel
from voteit.messaging.state import AppState
from voteit.messaging.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.decorators import on_transaction_commit
from voteit.notes.components import NotesComponent
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


@receiver(channel_subscribed, sender=AgendaItemChannel)
def send_notes_appstruct(*, context: AgendaItem, app_state: AppState, user, **kwargs):
    if context.meeting.component_enabled(NotesComponent.name):
        payloads = []
        for item in user.notes.filter(proposal__agenda_item=context).values(
            "pk", "proposal_id", "body", "intent", "created", "proposal__agenda_item_id"
        ):
            proposal_id = item.pop("proposal_id")
            agenda_item_id = item.pop("proposal__agenda_item_id")
            payloads.append(
                {
                    **item,
                    "proposal": proposal_id,
                    "user": user.id,
                    "meeting": context.meeting_id,
                    "agenda_item": agenda_item_id,
                }
            )
        app_state.add_batch(NoteChanged, payloads)
