# from __future__ import annotations
# from contextlib import suppress
# from typing import TYPE_CHECKING
#
# from django.core.exceptions import ObjectDoesNotExist
# from django.db.models.signals import post_save
# from django.db.models.signals import pre_delete
# from django.dispatch import receiver
# from envelope.signals import channel_subscribed
#
# from voteit.active.components import ActiveUsersComponent
# from voteit.active.messages import ActiveUserChanged
# from voteit.active.messages import ActiveUsers
# from voteit.active.models import ActiveUser
# from voteit.active.utils import active_enabled_for_meeting
# from voteit.components.models import MeetingComponent
# from voteit.core.decorators import disable_on_raw_save
# from voteit.core.decorators import on_transaction_commit
# from voteit.core.workflows import EnabledWf
# from voteit.meeting.channels import MeetingChannel
# from voteit.meeting.models import Meeting
# from voteit.meeting.models import MeetingRoles
#
# if TYPE_CHECKING:
#     from envelope.channels.models import AppState
#
#
# @receiver(channel_subscribed, sender=MeetingChannel)
# def send_active_users_appstruct(context: Meeting, app_state: AppState, **kwargs):
#     if active_enabled_for_meeting(context.meeting):
#         users = list(context.active_users.values_list("user_id", flat=True))
#         msg = ActiveUsers(users=users, meeting=context.pk)
#         app_state.append(msg)
#
#
# @receiver(post_save, sender=MeetingComponent)
# def send_active_state_when_enabled(instance: MeetingComponent, **kwargs):
#     if (
#         instance.component_name == ActiveUsersComponent.name
#         and instance.state == EnabledWf.ON
#     ):
#         users = list(instance.meeting.active_users.values_list("user_id", flat=True))
#         msg = ActiveUsers(users=users, meeting=instance.meeting.pk)
#         ch = MeetingChannel.from_instance(instance.meeting)
#         ch.sync_publish(msg)
#
#
# def _send_active_user(*, instance: ActiveUser, active: bool):
#     with suppress(ObjectDoesNotExist):
#         ch = MeetingChannel.from_instance(instance.meeting)
#         msg = ActiveUserChanged(
#             user=instance.user_id, active=active, meeting=instance.meeting.pk
#         )
#         ch.sync_publish(msg)
#
#
# @disable_on_raw_save
# @receiver(post_save, sender=ActiveUser)
# def _send_active_user_created(*, instance: ActiveUser, created, **kwargs):
#     if created:
#         _send_active_user(instance=instance, active=True)
#
#
# @on_transaction_commit
# @receiver(pre_delete, sender=ActiveUser)
# def _send_active_user_deleted(*, instance: ActiveUser, **kwargs):
#     _send_active_user(instance=instance, active=False)
#
#
# @receiver(pre_delete, sender=MeetingRoles)
# def remove_active_user(instance: MeetingRoles, **kwargs):
#     instance.context.active_users.filter(user=instance.user).delete()
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.models import AppState
from envelope.messages.common import Batch
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.decorators import on_transaction_commit
from voteit.notes.components import NotesComponent
from voteit.notes.messages import NoteAdded
from voteit.notes.messages import NoteChanged
from voteit.notes.messages import NoteDeleted
from voteit.notes.models import Note


@receiver(post_save, sender=Note)
@on_transaction_commit
def _send_created_updated(*, instance: Note, created: bool, **kwargs):
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
    if created:
        msg = NoteAdded(**data)
    else:
        msg = NoteChanged(**data)
    ch.sync_publish(msg)


@receiver(pre_delete, sender=Note)
def _send_deleted(*, instance: Note, **kwargs):
    ch = UserChannel(instance.user_id)
    msg = NoteDeleted(pk=instance.pk)
    ch.sync_publish(msg)


@receiver(channel_subscribed, sender=AgendaItemChannel)
def send_notes_appstruct(*, context: AgendaItem, app_state: AppState, user, **kwargs):
    if context.meeting.component_enabled(NotesComponent.name):
        batch = Batch(t=NoteAdded.name, payloads=[])
        for item in user.notes.filter(proposal__agenda_item=context).values(
            "pk", "proposal_id", "body", "intent", "created", "proposal__agenda_item_id"
        ):
            proposal_id = item.pop("proposal_id")
            agenda_item_id = item.pop("proposal__agenda_item_id")
            batch.append(
                NoteAdded(
                    **item,
                    proposal=proposal_id,
                    user=user.id,
                    meeting=context.meeting_id,
                    agenda_item=agenda_item_id,
                )
            )
        if batch.data.payloads:
            app_state.append(batch)
