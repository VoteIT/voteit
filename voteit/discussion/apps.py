from django.apps import AppConfig


class DiscussionConfig(AppConfig):
    name = "voteit.discussion"
    verbose_name = "Discussion"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.discussion import rules  # noqa
        from voteit.discussion.rest_api import views  # noqa
        from voteit.discussion import messages  # noqa
        from voteit.discussion import signals  # noqa
