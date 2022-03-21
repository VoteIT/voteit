from django.apps import AppConfig


class AccessPolicyConfig(AppConfig):
    name = "voteit.access_policy"

    def ready(self):
        from voteit.access_policy.app import policies
        from .rest_api import views
