from django.utils.translation import gettext_lazy as _

from voteit.core.role import roles, Role
from voteit.speaker.models import ListHandler
from voteit.speaker.rules import is_list_moderator


# @roles
# class ListModerator(Role):
#     """ Someone who can handle a specific speaker list.
#     """
#     model = ListHandler
#     m2m_field = "moderators"
#     title = _("Speaker list moderator")
#     name = "list_moderator"
#
#
# @roles
# class Speaker(Role):
#     """ May enter speaker lists.
#     """
#