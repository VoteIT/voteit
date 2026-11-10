"""
Blank a user's personal data without deleting the row.

For users who can't simply be deleted because content, votes or roles reference
them. Every reference and the pk stay, so meeting records stay intact; what
identifies the person goes.
"""

from __future__ import annotations

from logging import getLogger

from django.db import transaction
from django.utils.timezone import now

from voteit.core.sessions import end_user_access

logger = getLogger(__name__)


@transaction.atomic
def anonymise_user(user) -> None:
    """
    Blank the user row and the identity data of invites they used, and remove
    their login methods so nobody can get into the account again.
    """
    from voteit.invites.models import MeetingInvite

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
    # Holds the provider's uid, tokens and verified addresses.
    user.social_auth.all().delete()
    if image_name:
        storage = user._meta.get_field("image").storage
        transaction.on_commit(lambda: storage.delete(image_name))
    transaction.on_commit(lambda: end_user_access(user.pk))
    logger.info("Anonymised user %s", user.pk)
