from django.apps import AppConfig


class AccessPolicyConfig(AppConfig):
    name = 'voteit.access_policy'

    def ready(self):
        # Register policies
        from voteit.access_policy.app import policies
