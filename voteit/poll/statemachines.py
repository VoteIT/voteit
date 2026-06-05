from logging import getLogger

from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied
from pydantic import ValidationError as PydanticValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin
from voteit.poll.exceptions import ElectoralRegisterManualError
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollSettings

logger = getLogger(__name__)


class PollStateMachine(StateChart, TransitionSignalMixin):
    catch_errors_as_events = False

    private = State(value="private", name=_("Private"), initial=True)
    upcoming = State(value="upcoming", name=_("Upcoming"))
    ongoing = State(value="ongoing", name=_("Ongoing"))
    closed = State(value="closed", name=_("Closed"))
    finished = State(value="finished", name=_("Finished"))
    withheld = State(value="withheld", name=_("Withheld"))
    canceled = State(value="canceled", name=_("Canceled"))
    failed = State(value="failed", name=_("Failed"))
    no_result = State(value="no_result", name=_("No result"), final=True)

    # User-triggered events
    make_upcoming = Event(
        private.to(
            upcoming, validators=["has_change_state_permission", "validate_settings"]
        ),
        name=_("Make upcoming"),
    )
    make_ongoing = Event(
        upcoming.to(
            ongoing,
            validators=[
                "has_change_state_permission",
                "validate_settings",
                "validate_er_policy",
                "manual_er_not_needed",
                "validate_method",
            ],
        )
        | private.to(
            ongoing,
            validators=[
                "has_change_state_permission",
                "validate_settings",
                "validate_er_policy",
                "manual_er_not_needed",
                "validate_method",
            ],
        ),
        name=_("Start"),
    )
    close = Event(
        ongoing.to(closed, validators=["has_change_state_permission"])
        | failed.to(closed, validators=["has_change_state_permission"])
        | canceled.to(closed, validators=["has_change_state_permission"]),
        name=_("Close"),
    )
    publish_result = Event(
        withheld.to(finished, validators=["has_change_state_permission"]),
        name=_("Publish result"),
    )
    withhold_result = Event(
        finished.to(withheld, validators=["has_change_state_permission"]),
        name=_("Withold detailed result"),
    )
    cancel = Event(
        ongoing.to(canceled, validators=["has_change_state_permission"]),
        name=_("Cancel"),
    )
    unpublish = Event(
        upcoming.to(private, validators=["has_change_state_permission"]),
        name=_("Revert to private"),
    )

    # Internal-only events — not reachable via the REST API (guarded by not_allowed).
    # These define the valid state-graph paths for finished/withheld/no_result/failed,
    # which are actually executed via direct model.state assignment in _finish()/_no_result().
    finish = Event(
        closed.to(finished, validators=["not_allowed"]),
        name=_("Finish"),
    )
    finish_withheld = Event(
        closed.to(withheld, validators=["not_allowed"]),
        name=_("Finish (withheld)"),
    )
    mark_no_result = Event(
        closed.to(no_result, validators=["not_allowed"]),
        name=_("No result"),
    )
    fail = Event(
        private.to(failed, validators=["not_allowed"])
        | upcoming.to(failed, validators=["not_allowed"])
        | ongoing.to(failed, validators=["not_allowed"])
        | closed.to(failed, validators=["not_allowed"])
        | finished.to(failed, validators=["not_allowed"])
        | withheld.to(failed, validators=["not_allowed"])
        | canceled.to(failed, validators=["not_allowed"]),
        name=_("Failed"),
    )

    permissive_states = frozenset({"private", "upcoming"})
    finished_states = frozenset({"finished", "withheld"})

    # --- Validators ---

    def has_change_state_permission(self, *, user=None, force=False, **kw):
        if force:
            return
        perm = self.model.PERM_CHANGE_STATE
        if not user.has_perm(perm, self.model):
            raise PermissionDenied(perm_denied_msg(perm, self.model))

    def validate_settings(self, **kw):
        try:
            self.model.settings  # Will raise exceptions on bad settings
        except PydanticValidationError as exc:
            raise InvalidPollSettings(
                {"event": InvalidPollSettings.default_detail}
            ) from exc

    def validate_er_policy(self, **kw):
        if self.model.meeting_id is None:
            return  # Skip for unittests
        from voteit.poll.utils import get_electoral_policy_registry

        if self.model.meeting.er_policy_name not in get_electoral_policy_registry():
            raise ElectoralRegisterMissing(
                {"event": ElectoralRegisterMissing.default_detail}
            )

    def manual_er_not_needed(self, **kw):
        if (
            self.model.meeting_id  # Skip unittests!
            and not self.model.meeting.latest_er
            and self.model.meeting.er_policy.require_manual
        ):
            raise ElectoralRegisterManualError(
                {"event": ElectoralRegisterManualError.default_detail}
            )

    def not_allowed(self, **kw):
        raise PermissionDenied("This transition is not available via the API.")

    def validate_method(self, **kw):
        self.model.method.start_check()

    def on_enter_closed(self, **kw):
        self._complete_closed_poll()

    def on_enter_ongoing(self):
        try:
            er_policy = self.model.meeting.er_policy
        except (KeyError, AttributeError):
            logger.warning("Poll %s lacks valid meeting or er policy", self.model)
            return
        er_policy.apply(self.model)

    def _complete_closed_poll(self):
        """Auto-transition from closed to finished, withheld, or no_result."""
        if self.model.electoral_register is None:
            self.model._no_result()
            return
        self.model.vote_cleanup_set().delete()
        if self.model.votes.filter(abstain=False).count():
            self.model._finish()
        else:
            self.model._no_result()

    def on_make_upcoming(self, **kw):
        self.model._lock_proposals()

    def on_make_ongoing(self, **kw):
        self.model.started = now()
        self.model._lock_proposals()

    def on_close(self, **kw):
        self.model._mark_closed()

    def on_cancel(self, **kw):
        self.model._mark_closed()
        self.model._publish_proposals()

    def on_unpublish(self, **kw):
        self.model._publish_proposals()

    def on_publish_result(self, **kw):
        self.model.set_proposals_from_result()
        self.model.withheld_result = False

    def on_withhold_result(self, **kw):
        self.model.withheld_result = True
