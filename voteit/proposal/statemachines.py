from rest_framework.exceptions import PermissionDenied
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import PERM
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin
from voteit.proposal import PERM_RETRACT


class ProposalStateMachine(StateChart, TransitionSignalMixin):
    catch_errors_as_events = False

    published = State(value="published", name="Published", initial=True)
    retracted = State(value="retracted", name="Retracted")
    voting = State(value="voting", name="Voting")
    approved = State(value="approved", name="Approved")
    denied = State(value="denied", name="Denied")
    unhandled = State(value="unhandled", name="Unhandled")

    retract = Event(
        published.to(retracted, validators=["has_retract_permission"]),
        name="Retract",
    )
    lock_for_vote = Event(
        published.to(voting, validators=["has_change_permission"])
        | retracted.to(voting, validators=["has_change_permission"]),
        name="Lock for vote",
    )
    # Event names differ from state names to avoid class-attribute clash
    approve = Event(
        published.to(approved, validators=["has_change_permission"])
        | voting.to(approved, validators=["has_change_permission"])
        | denied.to(approved, validators=["has_change_permission"]),
        name="Approve",
    )
    deny = Event(
        published.to(denied, validators=["has_change_permission"])
        | voting.to(denied, validators=["has_change_permission"])
        | approved.to(denied, validators=["has_change_permission"]),
        name="Deny",
    )
    mark_unhandled = Event(
        published.to(unhandled, validators=["has_change_permission"]),
        name="Mark as unhandled",
    )
    publish = Event(
        retracted.to(published, validators=["has_change_permission"])
        | voting.to(published, validators=["has_change_permission"])
        | approved.to(published, validators=["has_change_permission"])
        | denied.to(published, validators=["has_change_permission"])
        | unhandled.to(published, validators=["has_change_permission"]),
        name="Publish",
    )

    def has_change_permission(self, *, user=None, force=False, **kw):
        if force:
            return
        perm = self.model.get_perm(PERM.CHANGE)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def has_retract_permission(self, *, user=None, force=False, **kw):
        if force:
            return
        perm = self.model.get_perm(PERM_RETRACT)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))
