from django.utils.translation import gettext as _

from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.registries import er_policy


@er_policy
class AutoBeforePoll(ElectoralRegisterPolicy):
    """ Create an electoral register when a poll enters upcoming or ongoing state,
        if it's needed. Set the latest created register for that poll and any other upcoming.
    """
    title = _("Automatic before poll")
