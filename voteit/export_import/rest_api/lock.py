from django.utils.translation import gettext_lazy as _
from voteit.core.rest_api.lock import RequestLock

import_lock = RequestLock(
    "meeting_data",
    already_running_message=_("Import already in progress for this session."),
    cooldown_message=_("Please wait a few seconds before running another import."),
)
