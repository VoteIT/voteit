from django.utils.translation import gettext_lazy as _

from voteit.core.role import roles, Role
from voteit.speaker.models import SpeakerListSystem


@roles
class ListModerator(Role):
    """ Someone who can handle all lists related to a speaker lists system.
    """
    model = SpeakerListSystem
    m2m_field = "moderators"
    title = _("Speaker list moderator")
    name = "list_moderator"


@roles
class Speaker(Role):
    """ May enter speaker lists.
    """
    model = SpeakerListSystem
    m2m_field = "speakers"
    title = _("Speaker")
    name = "speaker"
