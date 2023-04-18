from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class InvitesConfig(AppConfig):
    name = "voteit.invites"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .rest_api import views
        from voteit.invites import rules
        from voteit.invites import signals
        from voteit.invites.app import invites

        invites.register()
