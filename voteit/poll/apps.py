from django.apps import AppConfig


class PollConfig(AppConfig):
    name = "voteit.poll"
    verbose_name = "Polls"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.poll import rules
        from voteit.poll.rest_api import views
        from voteit.poll import channels
        from voteit.poll import messages
        from voteit.poll import signals
        from voteit.poll.app.polls import register

        register()

        from voteit.poll.app.er_policies import register

        register()
