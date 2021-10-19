from __future__ import annotations
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.access_policy.channels import MeetingInvitesChannel
from voteit.access_policy.messages import MeetingInviteAdded
from voteit.access_policy.messages import MeetingInviteChanged
from voteit.access_policy.messages import MeetingInviteDeleted
from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.rest_api.serializers import MeetingInviteSerializer
from voteit.access_policy.workflows import InviteWf
from voteit.meeting.signals import archive_meeting
from voteit.messaging.signals import channel_subscribed

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.meeting.models import Meeting
    from voteit.messaging.messages.app_state import AppState


@receiver(archive_meeting)
def expire_unused_invites(meeting, **kw):
    # Note: This will bypass the transaction, but that should be fine. Remember to change if we need to.
    meeting.invites.filter(state=InviteWf.OPEN).update(state=InviteWf.EXPIRED)


@receiver(channel_subscribed, sender=MeetingInvitesChannel)
def invites_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    # FIXME: We may not want to load all invites unless they're needed
    app_state.append_from_queryset(
        context.invites.all(),
        MeetingInviteSerializer,
        MeetingInviteAdded,
    )


@receiver(post_save, sender=MeetingInvite)
def meeting_invite_changed(instance: MeetingInvite = None, created=None, **kw):
    ch = MeetingInvitesChannel.from_instance(instance.meeting)
    data = MeetingInviteSerializer(instance).data
    if created:
        msg = MeetingInviteAdded({}, **data)
    else:
        msg = MeetingInviteChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=MeetingInvite)
def agenda_delete(instance: MeetingInvite = None, **kw):
    ch = MeetingInvitesChannel.from_instance(instance.meeting)
    msg = MeetingInviteDeleted({}, pk=instance.pk)
    ch.publish(msg)
