# TODO: Do we want these exceptions or something else that's transmittable?


class PollError(Exception):
    """ There's something wrong with a poll. """


class ElectoralRegisterMissing(PollError):
    pass


class ElectoralRegisterEmpty(PollError):
    pass


class InvalidPollMethod(PollError):
    pass


class InvalidProposalCount(PollError):
    pass


class NotAllowedToVote(PollError):
    """User isn't in the electoral register."""


class PollNotFinished(PollError):
    """Access to this method isn't allowed until the poll has closed and there's an actual result."""


class BallotChecksumError(PollError):
    """Checksum doesn't match or doesn't exist."""
