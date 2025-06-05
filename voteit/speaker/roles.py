from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role


ROLE_LIST_MODERATOR = Role("list_moderator", title=_("List moderator"))
ROLE_SPEAKER = Role("speaker", title=_("Speaker"))
