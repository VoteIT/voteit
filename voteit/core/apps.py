from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    name = 'voteit.core'
    verbose_name = _('VoteIT Core')

    def ready(self):
        from voteit.core import rules
        from voteit.core import signals
