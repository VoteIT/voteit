import rules

from voteit.agenda.rules import ai_discussion_not_blocked
from voteit.agenda.rules import ai_not_archived
from voteit.agenda.rules import ai_not_private
from voteit.core import PERM
from voteit.core.rules import is_author
from voteit.discussion.models import DiscussionPost
from voteit.meeting.rules import is_discusser
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

rules.add_perm(
    DiscussionPost.get_perm(PERM.ADD),
    ai_not_archived
    & (is_moderator | (ai_not_private & ai_discussion_not_blocked & is_discusser)),
)
rules.add_perm(
    DiscussionPost.get_perm(PERM.CHANGE), is_moderator & meeting_not_archived
)
rules.add_perm(
    DiscussionPost.get_perm(PERM.DELETE),
    meeting_not_archived & (is_moderator | is_author),
)
