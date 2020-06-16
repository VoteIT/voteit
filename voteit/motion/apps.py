from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MotionConfig(AppConfig):
    name = "voteit.motion"
    verbose_name = _("Motion")

    def ready(self):
        from voteit.motion import roles
