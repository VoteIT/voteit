from logging import getLogger

from django.apps import AppConfig

logger = getLogger(__name__)


class MeetingConfig(AppConfig):
    name = "voteit.meeting"
    verbose_name = "Meeting"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.meeting import roles  # noqa
        from voteit.meeting import rules  # noqa
        from voteit.meeting import channels  # noqa
        from voteit.meeting import messages  # noqa
        from voteit.meeting import signals  # noqa
        from voteit.meeting.rest_api import views  # noqa
