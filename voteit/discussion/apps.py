from django.apps import AppConfig


class DiscussionConfig(AppConfig):
    name = "voteit.discussion"
    verbose_name = "Discussion"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.discussion import rules
        from .rest_api import views
        from voteit.discussion import messages
        from voteit.discussion import signals
