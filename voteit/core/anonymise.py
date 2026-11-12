"""
Blank a user's personal data without deleting the row.

For users who can't simply be deleted because content or roles reference
them. Every reference and the pk stay, so meeting records stay intact; what
identifies the person goes.
"""

from __future__ import annotations

from logging import getLogger

from django.db import models
from django.db import transaction
from django.utils.timezone import now

from voteit.core.sessions import end_user_access

logger = getLogger(__name__)


@transaction.atomic
def anonymise_user(user) -> None:
    """
    Blank the user row and the identity data of invites they used, delete their
    votes, and remove their login methods so nobody can get into the account
    again.
    """
    from voteit.invites.models import MeetingInvite
    from voteit.poll.jobs import schedule_poll_status_publish
    from voteit.poll.models import Vote
    from voteit.poll.statemachines import PollStateMachine

    image_name = user.image.name if user.image else None
    user.first_name = ""
    user.last_name = ""
    user.email = ""
    # Unique and required, so it can't be blank.
    user.username = f"removed-{user.pk}"
    user.userid = None
    user.identity_id = None
    user.img_url = None
    user.image = None
    user.set_unusable_password()
    user.is_active = False
    user.is_staff = False
    user.is_superuser = False
    user.anonymised = now()
    user.save()
    for invite in MeetingInvite.objects.filter(used_by=user).exclude(user_data={}):
        invite.user_data = {}
        invite.save(update_fields=["user_data", "modified"])
    # Closed polls keep their ballots and result on the poll, so only ongoing
    # ones change -- their vote count needs publishing.
    votes = Vote.objects.filter(user=user)
    ongoing_poll_pks = set(
        votes.filter(poll__state=PollStateMachine.ongoing.value).values_list(
            "poll_id", flat=True
        )
    )
    votes.delete()
    for poll_pk in ongoing_poll_pks:
        transaction.on_commit(
            lambda poll_pk=poll_pk: schedule_poll_status_publish(poll_pk)
        )
    # Holds the provider's uid, tokens and verified addresses.
    user.social_auth.all().delete()
    if image_name:
        storage = user._meta.get_field("image").storage
        transaction.on_commit(lambda: storage.delete(image_name))
    blank_actor_details(user.pk)
    transaction.on_commit(lambda: end_user_access(user.pk))
    logger.info("Anonymised user %s", user.pk)


def blank_actor_details(user_pk: int) -> int:
    """
    Remove the email and IP address auditlog stores on entries the user made.
    The entries themselves stay until archive_auditlog removes them, see voteit.stats.archive.
    Also run on every user delete, see signals.py.
    """
    from auditlog.models import LogEntry

    return (
        LogEntry.objects.filter(actor_id=user_pk)
        .filter(
            models.Q(actor_email__isnull=False) | models.Q(remote_addr__isnull=False)
        )
        .update(actor_email=None, remote_addr=None)
    )
