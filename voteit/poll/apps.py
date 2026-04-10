from django.apps import AppConfig


class PollConfig(AppConfig):
    name = "voteit.poll"
    verbose_name = "Polls"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.poll import rules  # noqa
        from voteit.poll.rest_api import views  # noqa
        from voteit.poll import messages  # noqa
        from voteit.poll import signals  # noqa
        from voteit.poll.app.polls import register

        register()
        from voteit.poll.app.er_policies import register

        register()
