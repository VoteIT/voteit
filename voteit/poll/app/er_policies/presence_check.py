from __future__ import annotations

from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.registries import er_policy


__all__ = ("PresenceCheckPolicy",)

logger = getLogger(__name__)


@er_policy
class PresenceCheckPolicy(ElectoralRegisterPolicy):
    """
    The presence app is gone. Kept registered so old meetings and electoral
    registers with source "presence_check" still resolve to a title.
    """

    name = "presence_check"
    title = _("Presence check")
    description = _(
        "Any user who's both present and has the potential voter role will be added to the electoral "
        "register when it closes. "
        "If group votes is activated, the votes will be distributed equally between present members."
    )
    logger = logger
    allow_manual = True
    require_manual = True
    handles_vote_weight = True
    available = False

    def get_voters(self, **kwargs) -> dict[int, int]:
        raise ElectoralRegisterError("Presence check is no longer supported")
