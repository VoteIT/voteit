from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import NOT_ALLOWED_SM_GUARD
from voteit.core import PERM
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin


class SpeakerSystemStateMachine(StateChart, TransitionSignalMixin):
    catch_errors_as_events = False

    inactive = State(value="inactive", name="Inactive")
    active = State(value="active", name="Active", initial=True)
    archived = State(value="archived", name="Archived", final=True)

    activate = Event(
        inactive.to(active, validators=["has_change_permission"]), name="Make active"
    )
    inactivate = Event(
        active.to(inactive, validators=["has_change_permission", "no_active_speaker"]),
        name="Inactivate",
    )
    # Script-only: not exposed via REST. Model.archive() uses direct state assignment.
    archive = Event(
        inactive.to(archived, cond=[NOT_ALLOWED_SM_GUARD])
        | active.to(archived, cond=[NOT_ALLOWED_SM_GUARD]),
        name="Archive",
    )

    def has_change_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.CHANGE)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def no_active_speaker(self, **kw):
        if self.model.active_list and self.model.active_list.active_speaker():
            raise ValidationError({"event": [_("Deactivate active speaker first")]})

    def not_allowed(self, force=False, **kw):
        return force

    def on_inactivate(self, **kw):
        self.model.active_list = None
