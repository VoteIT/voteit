from django.apps import AppConfig


class OrganisationConfig(AppConfig):
    name = "voteit.organisation"
    verbose_name = "Organisation"

    def ready(self):
        # Make sure code is imported + registered
        from voteit.organisation import roles
        from voteit.organisation import rules
        from voteit.organisation import rest_api
        from voteit.organisation import providers
