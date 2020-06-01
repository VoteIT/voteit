from django.apps import AppConfig


class AccessPolicyConfig(AppConfig):
    name = 'voteit.access_policy'

    def ready(self):
        # Enable signals
        from voteit.access_policy import signals
        from voteit.access_policy.app import policies
