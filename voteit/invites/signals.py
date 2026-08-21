from __future__ import annotations

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.messages import MeetingInviteDeleted
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.invites.statemachines import InviteStateMachine
from voteit.meeting.models import MeetingRoles
from voteit.meeting.signals import archive_meeting
from voteit.meeting.signals import meeting_joined


@receiver(archive_meeting)
def expire_unused_invites(meeting, **kw):
    # Note: This will bypass the transaction, but that should be fine. Remember to change if we need to.
    meeting.invites.filter(state=InviteStateMachine.open.id).update(
        state=InviteStateMachine.expired.id
    )


@receiver(meeting_joined)
def auto_use_invite(meeting, user, **kw):
    if user.email:
        invite = meeting.invites.find_open_invites(email=[user.email]).first()
        if invite is not None:
            invite.accept(user)
            invite.save()


@receiver(post_save, sender=MeetingInvite)
@disable_on_raw_save
@on_transaction_commit
def meeting_invite_changed(instance: MeetingInvite = None, **kw):
    ch = MeetingInvitesChannel(instance.meeting_id)
    data = MeetingInviteSerializer(instance).data
    ch.sync_publish(MeetingInviteChanged(payload=data), on_commit=False)  # No need


@receiver(pre_delete, sender=MeetingInvite)
def agenda_delete(instance: MeetingInvite = None, **kw):
    ch = MeetingInvitesChannel(instance.meeting_id)
    msg = MeetingInviteDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)


@receiver(pre_delete, sender=MeetingRoles)
def cleanup_invites_when_user_removed_from_meeting(instance: MeetingRoles, **kw):
    MeetingInvite.objects.filter(
        used_by=instance.user, meeting=instance.context
    ).delete()
