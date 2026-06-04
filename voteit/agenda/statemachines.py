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
from voteit.meeting.workflows import MeetingWf
from voteit.poll.workflows import PollWf


class AgendaItemStateMachine(StateChart, TransitionSignalMixin):
    # Propagate signal handler exceptions (e.g. ValidationError from before_sm_transition)
    # instead of swallowing them as StateChart does by default.
    catch_errors_as_events = False

    private = State(value="private", name=_("Private"), initial=True)
    upcoming = State(value="upcoming", name=_("Upcoming"))
    ongoing = State(value="ongoing", name=_("Ongoing"))
    closed = State(value="closed", name=_("Closed"))
    archived = State(value="archived", name=_("Archived"), final=True)

    make_upcoming = Event(
        private.to(upcoming, validators=["has_change_permission"])
        | closed.to(upcoming, validators=["has_change_permission"])
        | ongoing.to(
            upcoming, validators=["has_change_permission", "no_ongoing_polls"]
        ),
        name=_("Make upcoming"),
    )
    unpublish = Event(
        upcoming.to(private, validators=["has_change_permission"])
        | closed.to(private, validators=["has_change_permission"])
        | ongoing.to(private, validators=["has_change_permission", "no_ongoing_polls"]),
        name=_("Unpublish"),
    )
    make_ongoing = Event(
        private.to(ongoing, validators=["has_change_permission", "meeting_is_ongoing"])
        | upcoming.to(
            ongoing, validators=["has_change_permission", "meeting_is_ongoing"]
        )
        | closed.to(
            ongoing, validators=["has_change_permission", "meeting_is_ongoing"]
        ),
        name=_("Make ongoing"),
    )
    close = Event(
        private.to(closed, validators=["has_change_permission", "no_ongoing_polls"])
        | upcoming.to(closed, validators=["has_change_permission", "no_ongoing_polls"])
        | ongoing.to(closed, validators=["has_change_permission", "no_ongoing_polls"]),
        name=_("Close"),
    )
    # Script-only: not exposed via REST. Model.archive() uses direct state assignment.
    archive = Event(
        private.to(archived, validators=["not_allowed"])
        | upcoming.to(archived, validators=["not_allowed"])
        | ongoing.to(archived, validators=["not_allowed"])
        | closed.to(archived, validators=["not_allowed"]),
        name=_("Archive"),
    )

    finished_states = frozenset({"closed", "archived"})
    archived_states = frozenset({"archived"})

    def has_change_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.CHANGE)
        if user.has_perm(perm, self.model):
            return True
        raise PermissionDenied(perm_denied_msg(perm, self.model))

    def no_ongoing_polls(self, **kw):
        if self.model.polls.filter(state=PollWf.ONGOING).exists():
            raise ValidationError({"transition": [_("There are ongoing polls")]})

    def meeting_is_ongoing(self, **kw):
        if self.model.meeting.state != MeetingWf.ONGOING:
            raise ValidationError({"transition": [_("Meeting must be ongoing")]})

    def not_allowed(self, **kw):
        raise PermissionDenied(_("This transition is not available via the API."))
