from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrganisationConfig(AppConfig):
    name = 'voteit.organisation'
    verbose_name = _('Organisation')

    def ready(self):
        # Make sure code is imported + registered
        from voteit.organisation import roles
        from voteit.organisation import rules
