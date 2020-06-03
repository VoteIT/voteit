from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role, roles
from voteit.meeting.models import Meeting
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import is_moderator


@roles
class Participant(Role):
    rule = is_participant
    model = Meeting
    m2m_field = "participants"
    title = _("Meeting participant")
    name = "participant"


@roles
class Moderator(Role):
    rule = is_moderator
    model = Meeting
    m2m_field = "moderators"
    title = _("Meeting moderator")
    name = "moderator"
