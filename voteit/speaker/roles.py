from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role
from voteit.speaker.models import SpeakerSystemRoles


ROLE_LIST_MODERATOR = Role("list_moderator", letter="m")
ROLE_SPEAKER = Role("speaker", letter="s")

SpeakerSystemRoles.add_valid(ROLE_LIST_MODERATOR, ROLE_SPEAKER)
