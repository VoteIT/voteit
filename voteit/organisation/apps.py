from django.apps import AppConfig
from django.conf import settings


class OrganisationConfig(AppConfig):
    name = "voteit.organisation"
    verbose_name = "Organisation"

    def ready(self):
        # Make sure code is imported + registered
        from voteit.organisation import roles
        from voteit.organisation import rules
        from voteit.organisation import rest_api
        from voteit.organisation import providers

        assert getattr(
            settings, "ID_HOST", None
        ), "ID_HOST required in settings. Specify as http://<url to id server>"
