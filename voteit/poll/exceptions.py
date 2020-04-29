

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
    """ User isn't in the electoral register.
    """
