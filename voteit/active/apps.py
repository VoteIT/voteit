from django.apps import AppConfig


class ActiveConfig(AppConfig):
    name = "voteit.active"
    verbose_name = "Active"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.active import components  # noqa
        from voteit.active import rules  # noqa
        from voteit.active import messages  # noqa
        from voteit.active import signals  # noqa
        from voteit.active.rest_api import views  # noqa
