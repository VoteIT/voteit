from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MeetingConfig(AppConfig):
    name = 'voteit.meeting'
    verbose_name = _('Meeting')

    def ready(self):
        from voteit.meeting import roles
        from voteit.meeting import rules
        from voteit.meeting import rest_api
