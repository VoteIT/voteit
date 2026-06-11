from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from django.utils.timezone import now
from rest_framework.exceptions import PermissionDenied
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError
from statemachine import Event
from statemachine import State
from statemachine import StateChart

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
                "meeting_and_ai_ongoing",
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
                "meeting_and_ai_ongoing",
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

    # These are auto-transitions: bare State.to(...) expressions that
    # python-statemachine evaluates immediately on entering `closed`, in
    # declaration order, taking the first whose `cond` passes.  They are
    # NOT user-triggered events — closing a poll always resolves to one of
    # withheld / finished / failed / no_result without any further action required.
    #
    # calculate_result() is called inside on_close (not here) so that errors can
    # be caught and logged without rolling back the ongoing → closed transition.
    # The `has_result` condition then routes here based on whether it succeeded.
    closed.to(
        withheld,
        cond=["is_withheld", "has_populated_er", "has_valid_votes", "has_result"],
    )
    closed.to(
        finished,
        cond=["!is_withheld", "has_populated_er", "has_valid_votes", "has_result"],
        on=["set_proposals_from_result"],
    )
    closed.to(no_result, cond=["!has_valid_votes"])
    closed.to(no_result, cond=["!has_populated_er"])
    # Fallback: ER and votes exist but result is still None — calculation error
    # was caught and logged in on_close.  Moderator can retry via the close event.
    closed.to(failed)

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

    def meeting_and_ai_ongoing(self, **kwargs):
        if self.model.meeting_id is None or self.model.agenda_item_id is None:
            return True  # Unittests, we don't care
        if not self.model.agenda_item.is_ongoing:
            raise ValidationError({"event": "Agenda item must be ongoing"})
        if not self.model.meeting.is_ongoing:
            raise ValidationError({"event": "Meeting must be ongoing"})

    # --- Conditions ---

    def is_withheld(self, **kw) -> bool:
        return self.model.withheld_result

    def has_valid_votes(self, **kw) -> bool:
        return self.model.votes.filter(abstain=False).exists()

    def has_populated_er(self) -> bool:
        if self.model.electoral_register is None:
            return False
        return bool(self.model.electoral_register.voter_data)

    def has_result(self, **kw) -> bool:
        return self.model.result_data is not None

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
        # Attempt calculation before auto-transitions evaluate.  Exceptions are
        # caught here so the ongoing → closed transition is not rolled back.
        # A failed calculation leaves result_data=None; the auto-transition to
        # `failed` then fires and the moderator can retry via the close event.
        if self.model.votes.filter(abstain=False).exists():
            try:
                self.model.calculate_result()
            except Exception:
                logger.exception("Poll %s: result calculation failed", self.model.pk)

    def on_enter_failed(self):
        # Clear any partial ballot data written by finalize_vote_data() before
        # the calculation error, so that retrying via close can re-finalize.
        self.model.ballot_data = None
        self.model.ballot_checksum = None
        self.model.abstains = 0

    def on_cancel(self, **kw):
        self.model.closed = now()
        self.model._publish_proposals()

    def on_publish_result(self, **kw):
        self.model.withheld_result = False

    def on_withhold_result(self, **kw):
        self.model.withheld_result = True
