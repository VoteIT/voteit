from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role
from voteit.organisation.models import Organisation, OrganisationRoles

__all__ = ("ROLE_ORG_MANAGER", "ROLE_MEETING_CREATOR")


ROLE_ORG_MANAGER = Role("org_manager")
ROLE_MEETING_CREATOR = Role("meeting_creator")


OrganisationRoles.add_valid(ROLE_ORG_MANAGER, ROLE_MEETING_CREATOR)



# @roles
# class OrgManager(Role):
#     model = Organisation
#     m2m_field = "managers"
#     title = _("Organisation manager")
#     name = "org_manager"
#
#
# @roles
# class MeetingCreator(Role):
#     model = Organisation
#     m2m_field = "meeting_creators"
#     title = _("Meeting creator")
#     name = "meeting_creator"
