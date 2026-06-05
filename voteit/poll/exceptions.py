from rest_framework.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PollError(ValidationError):
    """
    Base poll errors
    Based on DRFs exception so they'll work in rest views.
    """

    default_code = "poll_error"
    default_detail = _("Unknown poll error.")


class ElectoralRegisterError(ValidationError):
    """
    Base error for electoral registers.
    """

    default_code = "er_error"
    default_detail = _("Unknown electoral register error.")


class MeetingERMissingError(ValidationError):
    default_code = "er_meeting_error"
    default_detail = _("Electoral register settings missing for this meeting.")


class ElectoralRegisterMissing(PollError):
    default_code = "poll_er_missing"
    default_detail = _("Poll has no electoral register.")


class ElectoralRegisterEmpty(ElectoralRegisterError):
    default_code = "er_empty"
    default_detail = _("Electoral register is empty.")


class ElectoralRegisterManualError(PollError):
    default_code = "poll_er_manual"
    default_detail = _(
        "Electoral register must be created manually before starting a poll."
    )


class InvalidPollMethod(PollError):
    default_code = "poll_invalid_method"
    default_detail = _("Invalid poll method.")


class InvalidPollSettings(PollError):
    default_code = "poll_invalid_settings"
    default_detail = _("Invalid poll settings.")


class InvalidProposalCount(PollError):
    default_code = "poll_invalid_proposal_count"
    default_detail = _("Invalid proposal count.")


class NotAllowedToVote(PollError):
    default_code = "poll_not_allowed_to_vote"
    default_detail = "User isn't in the electoral register."


class PollNotFinished(PollError):
    default_code = "poll_not_finished"
    default_detail = "Access to this method isn't allowed until the poll has closed and there's an actual result."
