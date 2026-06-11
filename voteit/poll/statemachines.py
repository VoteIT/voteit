from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from django.utils.timezone import now
from rest_framework.exceptions import PermissionDenied
from pydantic import ValidationError as PydanticValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core import NOT_ALLOWED_SM_GUARD
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.core.statemachines import TransitionSignalMixin
from voteit.poll.exceptions import ElectoralRegisterManualError
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollSettings

if TYPE_CHECKING:
    from voteit.poll.models import Poll

logger = getLogger(__name__)


class PollStateMachine(StateChart, TransitionSignalMixin):
    model: Poll
    catch_errors_as_events = False  # We want to propagate as ValidationErrors
    validate_final_reachability = False  # withheld <-> finished makes this impossible

    private = State(value="private", name="Private", initial=True)
    upcoming = State(value="upcoming", name="Upcoming")
    ongoing = State(value="ongoing", name="Ongoing")
    closed = State(value="closed", name="Closed")
    finished = State(value="finished", name="Finished")
    withheld = State(value="withheld", name="Withheld")
    canceled = State(value="canceled", name="Canceled")
    failed = State(value="failed", name="Failed")
    no_result = State(value="no_result", name="No result", final=True)

    # User-triggered events
    make_upcoming = Event(
        private.to(
            upcoming, validators=["has_change_state_permission", "validate_settings"]
        ),
        name="Make upcoming",
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
        name="Start",
    )
    close = Event(
        ongoing.to(closed, validators=["has_change_state_permission"])
        | failed.to(closed, validators=["has_change_state_permission"])
        | canceled.to(closed, validators=["has_change_state_permission"]),
        name="Close",
    )
    publish_result = Event(
        withheld.to(
            finished,
            validators=["has_change_state_permission"],
            on=["set_proposals_from_result"],
        ),
        name="Publish result",
    )
    withhold_result = Event(
        finished.to(withheld, validators=["has_change_state_permission"]),
        name="Withold detailed result",
    )
    cancel = Event(
        ongoing.to(canceled, validators=["has_change_state_permission"]),
        name="Cancel",
    )
    unpublish = Event(
        upcoming.to(private, validators=["has_change_state_permission"]),
        name="Revert to private",
    )

    # Auto-transitions
    closed.to(
        withheld,
        cond=["is_withheld", "has_populated_er", "has_valid_votes"],
        on=["calculate_result"],
    )
    closed.to(
        finished,
        cond=["!is_withheld", "has_populated_er", "has_valid_votes"],
        on=["calculate_result", "set_proposals_from_result"],
    )
    closed.to(no_result, cond=["!has_valid_votes"])

    fail = Event(closed.to(failed, cond=[NOT_ALLOWED_SM_GUARD]), name="Failed")

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

    def validate_method(self, **kw):
        self.model.method.start_check()

    # --- Conditions ---

    def not_allowed(self, force=False, **kw):
        return force

    def is_withheld(self, **kw) -> bool:
        return self.model.withheld_result

    def has_valid_votes(self, **kw) -> bool:
        if not hasattr(self.model, "_valid_votes"):
            self.model._valid_votes = self.model.votes.filter(abstain=False).exists()
        return self.model._valid_votes

    def has_populated_er(self) -> bool:
        if self.model.electoral_register is None:
            return False
        return bool(self.model.electoral_register.voter_data)

    # --- Actions ---
    def on_enter_ongoing(self):
        try:
            er_policy = self.model.meeting.er_policy
        except (KeyError, AttributeError):
            logger.warning("Poll %s lacks valid meeting or er policy", self.model)
            return
        er_policy.apply(self.model)

    def on_make_upcoming(self, **kw):
        self.model._lock_proposals()

    def on_make_ongoing(self, **kw):
        self.model.started = now()
        self.model._lock_proposals()

    def on_close(self, **kw):
        self.model.closed = now()
        if self.model.electoral_register is not None:
            self.model.cleanup_removed_from_er_votes()

    def on_cancel(self, **kw):
        self.model.closed = now()
        self.model._publish_proposals()

    def on_publish_result(self, **kw):
        self.model.withheld_result = False

    def on_withhold_result(self, **kw):
        self.model.withheld_result = True
