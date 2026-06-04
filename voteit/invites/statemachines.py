from __future__ import annotations
from typing import TYPE_CHECKING

from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import PERM
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin
from voteit.invites.utils import get_invite_adapter_registry

if TYPE_CHECKING:
    from voteit.core.models import User


class InviteStateMachine(StateChart, TransitionSignalMixin):
    open = State(value="open", name=_("Open"), initial=True)
    accepted = State(value="accepted", name=_("Accepted"), final=True)
    rejected = State(value="rejected", name=_("Rejected"), final=True)
    revoked = State(value="revoked", name=_("Revoked"), final=True)
    expired = State(value="expired", name=_("Expired"), final=True)

    accept = Event(open.to(accepted), name=_("Accept"))
    reject = Event(open.to(rejected), name=_("Reject"))
    revoke = Event(
        open.to(revoked, validators=["has_change_permission"]), name=_("Revoke")
    )
    expire = Event(open.to(expired), name=_("Expire"))

    def after_accept(self, *, user):
        self.model.used_by = user
        self.model.used_at = now()
        self.model.meeting.add_roles(user, *self.model.roles)
        reg = get_invite_adapter_registry()
        reg.run_accepted(self.model)

    def after_reject(self, *, user):
        if not user:
            return
        if user.pk is not None:
            self.model.used_by = user

    def has_change_permission(self, *, user: User, force: bool = False):
        if force:
            return True
        perm = self.model.get_perm(PERM.CHANGE)
        if user.has_perm(perm, self.model):
            return True
        raise PermissionDenied(perm_denied_msg(perm, self.model))
