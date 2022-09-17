from __future__ import annotations

import rules

from voteit.components.permissions import MeetingComponentPermissions
from voteit.components.permissions import OrganisationComponentPermissions
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_org_user


rules.add_perm(MeetingComponentPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(MeetingComponentPermissions.VIEW, can_view_meeting)
rules.add_perm(MeetingComponentPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(MeetingComponentPermissions.DELETE, meeting_not_archived & is_moderator)

rules.add_perm(OrganisationComponentPermissions.ADD, is_manager)
rules.add_perm(OrganisationComponentPermissions.VIEW, is_org_user)
rules.add_perm(OrganisationComponentPermissions.CHANGE, is_manager)
rules.add_perm(OrganisationComponentPermissions.DELETE, is_manager)
