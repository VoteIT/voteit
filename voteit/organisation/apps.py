from urllib.parse import urlparse

from django.apps import AppConfig
from django.conf import settings


class OrganisationConfig(AppConfig):
    name = "voteit.organisation"
    verbose_name = "Organisation"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.organisation import roles  # noqa
        from .rest_api import views  # noqa
        from . import channels  # noqa
        from . import messages  # noqa
        from . import signals  # noqa

        assert getattr(settings, "ID_HOST", None), (
            "ID_HOST required in settings. Specify as http://<url to id server>"
        )
        parsed = urlparse(settings.ID_HOST)
        assert parsed.scheme in (
            "http",
            "https",
        ), "ID_HOST must be http or https scheme"
