from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import PERM
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin


class AgendaItemStateMachine(StateChart, TransitionSignalMixin):
    # Propagate signal handler exceptions (e.g. ValidationError from before_sm_transition)
    # instead of swallowing them as StateChart does by default.
    catch_errors_as_events = False

    private = State(value="private", name="Private", initial=True)
    upcoming = State(value="upcoming", name="Upcoming")
    ongoing = State(value="ongoing", name="Ongoing")
    closed = State(value="closed", name="Closed")
    archived = State(value="archived", name="Archived", final=True)

    make_upcoming = Event(
        private.to(upcoming, validators=["has_change_permission"])
        | closed.to(upcoming, validators=["has_change_permission"])
        | ongoing.to(
            upcoming, validators=["has_change_permission", "no_ongoing_polls"]
        ),
        name="Make upcoming",
    )
    unpublish = Event(
        upcoming.to(private, validators=["has_change_permission"])
        | closed.to(private, validators=["has_change_permission"])
        | ongoing.to(private, validators=["has_change_permission", "no_ongoing_polls"]),
        name="Unpublish",
    )
    make_ongoing = Event(
        private.to(
            ongoing, cond=["meeting_is_ongoing"], validators=["has_change_permission"]
        )
        | upcoming.to(
            ongoing, cond=["meeting_is_ongoing"], validators=["has_change_permission"]
        )
        | closed.to(
            ongoing, cond=["meeting_is_ongoing"], validators=["has_change_permission"]
        ),
        name="Make ongoing",
    )
    close = Event(
        private.to(
            closed,
            cond=["meeting_not_upcoming"],
            validators=["has_change_permission", "no_ongoing_polls"],
        )
        | upcoming.to(
            closed,
            cond=["meeting_not_upcoming"],
            validators=["has_change_permission", "no_ongoing_polls"],
        )
        | ongoing.to(
            closed,
            cond=["meeting_not_upcoming"],
            validators=["has_change_permission", "no_ongoing_polls"],
        ),
        name="Close",
    )
    # Script-only: not exposed via REST. Model.archive() uses direct state assignment.
    archive = Event(
        private.to(archived, cond=["not_allowed"])
        | upcoming.to(archived, cond=["not_allowed"])
        | ongoing.to(archived, cond=["not_allowed"])
        | closed.to(archived, cond=["not_allowed"]),
        name="Archive",
    )

    finished_states = frozenset({"closed", "archived"})
    archived_states = frozenset({"archived"})

    def has_change_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.CHANGE)
        if user.has_perm(perm, self.model):
            return True
        raise PermissionDenied(perm_denied_msg(perm, self.model))

    def no_ongoing_polls(self, **kw):
        if self.model.polls.filter(state="ongoing").exists():
            raise ValidationError({"transition": [_("There are ongoing polls")]})

    def meeting_is_ongoing(self, **kw):
        return self.model.meeting.is_ongoing

    def meeting_not_upcoming(self, **kw):
        return not self.model.meeting.is_upcoming

    def not_allowed(self, force=False, **kw):
        return force
