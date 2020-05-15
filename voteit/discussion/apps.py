from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DiscussionConfig(AppConfig):
    name = 'voteit.discussion'
    verbose_name = _('Discussion')
