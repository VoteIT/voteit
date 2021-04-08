from django.dispatch import receiver
from voteit.access_policy.workflows import InviteWf
from voteit.meeting.signals import archive_meeting


@receiver(archive_meeting)
def expire_unused_invites(meeting, **kw):
    # Note: This will bypass the transaction, but that should be fine. Remember to change if we need to.
    meeting.invites.filter(state=InviteWf.OPEN).update(state=InviteWf.EXPIRED)
