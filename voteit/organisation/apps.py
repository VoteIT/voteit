from urllib.parse import urlparse

from django.apps import AppConfig
from django.conf import settings


class OrganisationConfig(AppConfig):
    name = "voteit.organisation"
    verbose_name = "Organisation"

    def ready(self):
        # Make sure code is imported + registered
        from voteit.organisation import roles
        from voteit.organisation import rules
        from .rest_api import views
        from voteit.organisation import providers

        assert getattr(
            settings, "ID_HOST", None
        ), "ID_HOST required in settings. Specify as http://<url to id server>"
        parsed = urlparse(settings.ID_HOST)
        assert parsed.scheme in (
            "http",
            "https",
        ), "ID_HOST must be http or https scheme"
