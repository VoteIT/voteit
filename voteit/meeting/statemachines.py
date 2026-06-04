from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import PERM
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin


class MeetingStateMachine(StateChart, TransitionSignalMixin):
    catch_errors_as_events = False

    upcoming = State(value="upcoming", name=_("Upcoming"), initial=True)
    ongoing = State(value="ongoing", name=_("Ongoing"))
    closed = State(value="closed", name=_("Closed"))
    archiving = State(value="archiving", name=_("Archiving"))
    archived = State(value="archived", name=_("Archived"))
    deleting = State(value="deleting", name=_("Deleting"))

    make_upcoming = Event(
        ongoing.to(upcoming, validators=["has_moderate_permission"]),
        name=_("Back to upcoming"),
    )
    make_ongoing = Event(
        upcoming.to(ongoing, validators=["has_moderate_permission", "valid_er_policy"])
        | closed.to(ongoing, validators=["has_moderate_permission", "valid_er_policy"]),
        name=_("Make ongoing"),
    )
    close = Event(
        ongoing.to(closed, validators=["has_moderate_permission", "no_ongoing_polls"]),
        name=_("Close"),
    )
    request_archiving = Event(
        closed.to(archiving, validators=["has_archive_permission"]),
        name=_("Request archiving"),
    )
    abort_archiving = Event(
        archiving.to(closed, validators=["has_archive_permission"]),
        name=_("Abort archiving"),
    )
    request_delete = Event(
        upcoming.to(deleting, validators=["has_delete_permission"])
        | ongoing.to(deleting, validators=["has_delete_permission"])
        | closed.to(deleting, validators=["has_delete_permission"])
        | archiving.to(deleting, validators=["has_delete_permission"])
        | archived.to(deleting, validators=["has_delete_permission"]),
        name=_("Request delete..."),
    )
    abort_delete = Event(
        deleting.to(
            upcoming,
            cond="pre_delete_state_is_upcoming",
            validators=["has_delete_permission"],
        )
        | deleting.to(
            ongoing,
            cond="pre_delete_state_is_ongoing",
            validators=["has_delete_permission"],
        )
        | deleting.to(
            closed,
            cond="pre_delete_state_is_closed",
            validators=["has_delete_permission"],
        )
        | deleting.to(
            archiving,
            cond="pre_delete_state_is_archiving",
            validators=["has_delete_permission"],
        )
        | deleting.to(
            archived,
            cond="pre_delete_state_is_archived",
            validators=["has_delete_permission"],
        ),
        name=_("Abort delete"),
    )

    finished_states = frozenset({"closed", "archiving", "archived", "deleting"})
    archived_states = frozenset({"archiving", "archived", "deleting"})

    def has_moderate_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.MODERATE)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def has_archive_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.ARCHIVE)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def has_delete_permission(self, *, user, **kw):
        perm = self.model.get_perm(PERM.DELETE)
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def valid_er_policy(self, **kw):
        from voteit.poll.utils import get_electoral_policy_registry

        if self.model.er_policy_name not in get_electoral_policy_registry():
            raise ValidationError(
                {"transition": [_("Must have valid electoral register policy name")]}
            )

    def no_ongoing_polls(self, **kw):
        if self.model.polls.filter(state="ongoing").exists():
            raise ValidationError(
                {"transition": [_("Meeting has ongoing polls - close them first")]}
            )

    def pre_delete_state_is_upcoming(self, **kw):
        return self.model.pre_delete_state == MeetingStateMachine.upcoming.value

    def pre_delete_state_is_ongoing(self, **kw):
        return self.model.pre_delete_state == MeetingStateMachine.ongoing.value

    def pre_delete_state_is_closed(self, **kw):
        return self.model.pre_delete_state == MeetingStateMachine.closed.value

    def pre_delete_state_is_archiving(self, **kw):
        return self.model.pre_delete_state == MeetingStateMachine.archiving.value

    def pre_delete_state_is_archived(self, **kw):
        return self.model.pre_delete_state == MeetingStateMachine.archived.value

    def on_make_ongoing(self, **kw):
        self.model.start_time = timezone.now()

    def on_close(self, **kw):
        self.model.end_time = timezone.now()

    def on_request_archiving(self, **kw):
        self.model.archive_after = timezone.now() + timedelta(days=3)

    def on_abort_archiving(self, **kw):
        self.model.archive_after = None

    def on_request_delete(self, source, **kw):
        self.model.pre_delete_state = source.value
        self.model.delete_requested = timezone.now()

    def on_abort_delete(self, **kw):
        self.model.delete_requested = None
