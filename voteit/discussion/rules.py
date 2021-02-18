import rules

from voteit.agenda.rules import (
    ai_discussion_not_blocked,
    can_view_ai,
    ai_not_private,
    ai_not_archived,
)
from voteit.core.rules import is_author
from voteit.meeting.rules import (
    is_moderator,
    is_discusser,
    meeting_not_archived,
)
from voteit.discussion.permissions import DiscussionPermissions


rules.add_perm(
    DiscussionPermissions.ADD,
    ai_not_archived
    & (is_moderator | (ai_not_private & ai_discussion_not_blocked & is_discusser)),
)
rules.add_perm(DiscussionPermissions.VIEW, can_view_ai)
rules.add_perm(DiscussionPermissions.CHANGE, is_moderator & meeting_not_archived)
rules.add_perm(
    DiscussionPermissions.DELETE,
    meeting_not_archived & (is_moderator | is_author),
)
