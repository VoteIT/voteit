from logging import getLogger

from django.apps import AppConfig

logger = getLogger(__name__)


class MeetingConfig(AppConfig):
    name = "voteit.meeting"
    verbose_name = "Meeting"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.meeting import roles
        from voteit.meeting import rules
        from voteit.meeting.rest_api import views
        from voteit.meeting import channels
        from voteit.meeting import messages
        from voteit.meeting import signals
        from voteit.meeting.utils import get_named_path_dict

        get_named_path_dict()  # Will issue warnings
