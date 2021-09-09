from django.apps import AppConfig


class DiscussionConfig(AppConfig):
    name = "voteit.discussion"
    verbose_name = "Discussion"

    def ready(self):
        from voteit.discussion import rules
        from voteit.discussion import rest_api
        from voteit.discussion import messages
        from voteit.discussion import signals
