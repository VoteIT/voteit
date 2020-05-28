from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role, roles
from voteit.meeting.models import Meeting
from voteit.meeting.rules import is_participant


@roles
class Participant(Role):
    rule = is_participant
    model = Meeting
    m2m_field = "participants"
    title = _("Meeting participant")
