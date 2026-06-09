from django.utils.translation import gettext_lazy as _
from voteit.core.rest_api.lock import RequestLock

_already_running_message = _("Import already in progress.")
_cooldown_message = _("Please wait a few seconds before running another import.")
import_lock = RequestLock(
    "meeting_data",
    already_running_message=_already_running_message,
    cooldown_message=_cooldown_message,
)
import_preview_lock = RequestLock(
    "meeting_data_preview",
    already_running_message=_already_running_message,
    cooldown_message=_cooldown_message,
    cooldown_ttl=0,
    processing_ttl=60,
)
