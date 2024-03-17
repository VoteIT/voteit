from logging import getLogger

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = getLogger(__name__)


class ExportImportConfig(AppConfig):
    name = "voteit.export_import"
    verbose_name = "Export/Import"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        secret = getattr(settings, "EXPORT_SECRET_KEY", "")
        if not isinstance(secret, str):
            logger.warning(
                "EXPORT_SECRET_KEY in settings must be present to use export views"
            )
        from .rest_api import register

        register()
