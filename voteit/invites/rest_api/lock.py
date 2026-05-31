from django.utils.translation import gettext_lazy as _
from voteit.core.rest_api.lock import RequestLock

invites_lock = RequestLock(
    "meeting_invites",
    already_running_message=_("Invite operation already in progress."),
    cooldown_message=_("Please wait a few seconds before retrying."),
)
