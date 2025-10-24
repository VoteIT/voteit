from django.apps import AppConfig


class InvitesConfig(AppConfig):
    name = "voteit.invites"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .rest_api import views  # noqa
        from voteit.invites import rules  # noqa
        from voteit.invites import signals  # noqa
        from voteit.invites.app import invites

        invites.register()
