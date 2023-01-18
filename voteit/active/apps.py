from django.apps import AppConfig


class ActiveConfig(AppConfig):
    name = "voteit.active"
    verbose_name = "Active"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.active import components
        from voteit.active import rules
        from voteit.active import messages
        from voteit.active import signals
