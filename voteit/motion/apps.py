from django.apps import AppConfig


class MotionConfig(AppConfig):
    name = "voteit.motion"
    verbose_name = "Motion"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.motion import roles
        from voteit.motion import rules
