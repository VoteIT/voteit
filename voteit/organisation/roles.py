from django.utils.translation import gettext_lazy as _

from voteit.core.role import roles, Role
from voteit.organisation.models import Organisation
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_meeting_creator

__all__ = ("OrgManager", "MeetingCreator")


@roles
class OrgManager(Role):
    rule = is_manager
    model = Organisation
    m2m_field = "managers"
    title = _("Organisation manager")
    name = "org_manager"


@roles
class MeetingCreator(Role):
    rule = is_meeting_creator
    model = Organisation
    m2m_field = "meeting_creators"
    title = _("Meeting creator")
    name = "meeting_creator"
