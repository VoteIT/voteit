from django.apps import AppConfig


class AccessPolicyConfig(AppConfig):
    name = "voteit.access_policy"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.access_policy import rules  # noqa
        from voteit.access_policy.app import policies  # noqa
        from voteit.access_policy.rest_api import views  # noqa
