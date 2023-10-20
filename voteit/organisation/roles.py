from voteit.core.role import Role
from voteit.organisation.models import OrganisationRoles

__all__ = ("ROLE_ORG_MANAGER", "ROLE_MEETING_CREATOR")


ROLE_ORG_MANAGER = Role("org_manager", letter="m")
ROLE_MEETING_CREATOR = Role("meeting_creator", letter="c")


OrganisationRoles.add_valid(ROLE_ORG_MANAGER, ROLE_MEETING_CREATOR)
