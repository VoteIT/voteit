from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role

# from voteit.speaker.models import SpeakerSystemRoles


ROLE_LIST_MODERATOR = Role("list_moderator")
ROLE_SPEAKER = Role("speaker")

# SpeakerSystemRoles.add_valid(ROLE_LIST_MODERATOR, ROLE_SPEAKER)
