from django.apps import AppConfig


class InvitesConfig(AppConfig):
    name = "voteit.invites"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .rest_api import views
        from voteit.invites import rules
        from voteit.invites import signals
        from voteit.invites.app.invites import register

        register()
