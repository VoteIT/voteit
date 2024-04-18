from __future__ import annotations
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from envelope.messages.common import Batch
from envelope.signals import channel_subscribed
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteAdded
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.messages import MeetingInviteDeleted
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.workflows import InviteWf
from voteit.meeting.signals import archive_meeting
from voteit.meeting.signals import meeting_joined

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.meeting.models import Meeting
    from envelope.utils import AppState


@receiver(archive_meeting)
def expire_unused_invites(meeting, **kw):
    # Note: This will bypass the transaction, but that should be fine. Remember to change if we need to.
    meeting.invites.filter(state=InviteWf.OPEN).update(state=InviteWf.EXPIRED)


@receiver(meeting_joined)
def auto_use_invite(meeting, user, **kw):
    if user.email:
        invite = meeting.invites.find_open_invites(email=[user.email]).first()
        if invite is not None:
            invite.accept(user)
            invite.save()


@receiver(channel_subscribed, sender=MeetingInvitesChannel)
def invites_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    # FIXME: We may not want to load all invites unless they're needed
    reg = get_invite_adapter_registry()
    invites_qs = reg.prep_invites_qs_for_subscribe(context.invites.all())
    serializer = MeetingInviteSerializer(invites_qs, many=True)
    if serializer.data:
        batch = Batch(t=MeetingInviteAdded.name, payloads=[])
        for item in serializer.data:
            batch.append(MeetingInviteAdded(**item))
        app_state.append(batch)


@receiver(post_save, sender=MeetingInvite)
@disable_on_raw_save
@on_transaction_commit
def meeting_invite_changed(instance: MeetingInvite = None, created=None, **kw):
    ch = MeetingInvitesChannel(instance.meeting_id)
    data = MeetingInviteSerializer(instance).data
    if created:
        msg = MeetingInviteAdded(data=data)
    else:
        msg = MeetingInviteChanged(data=data)
    ch.sync_publish(msg, on_commit=False)  # No need


@receiver(pre_delete, sender=MeetingInvite)
def agenda_delete(instance: MeetingInvite = None, **kw):
    ch = MeetingInvitesChannel(instance.meeting_id)
    msg = MeetingInviteDeleted(pk=instance.pk)
    ch.sync_publish(msg)
