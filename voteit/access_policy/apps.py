from django.apps import AppConfig


class AccessPolicyConfig(AppConfig):
    name = "voteit.access_policy"

    def ready(self):
        from voteit.access_policy.app import policies
        from voteit.access_policy import rest_api
        from voteit.access_policy import invite
        from voteit.access_policy import rules
        from voteit.access_policy import signals
