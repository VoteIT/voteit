from django.utils.translation import gettext_lazy as _

from voteit.core.role import roles, Role
from voteit.organisation.models import Organisation

__all__ = ("OrgManager", "MeetingCreator")


@roles
class OrgManager(Role):
    model = Organisation
    m2m_field = "managers"
    title = _("Organisation manager")
    name = "org_manager"


@roles
class MeetingCreator(Role):
    model = Organisation
    m2m_field = "meeting_creators"
    title = _("Meeting creator")
    name = "meeting_creator"
