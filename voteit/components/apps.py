from django.apps import AppConfig


class ComponentsConfig(AppConfig):
    name = "voteit.components"
    verbose_name = "Components"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.components import rules  # noqa
        from voteit.components.rest_api import views  # noqa
        from voteit.components import messages  # noqa
        from voteit.components import signals  # noqa
        from voteit.components.app.components import register

        register()
