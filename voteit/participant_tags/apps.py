from logging import getLogger

from django.apps import AppConfig

logger = getLogger(__name__)


class ParticipantTagConfig(AppConfig):
    name = "voteit.participant_tags"
    verbose_name = "Participant tag"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import components  # noqa
        from . import messages  # noqa
        from . import signals  # noqa
        from .rest_api import views  # noqa
