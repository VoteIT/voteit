

class PollPermissions:
    ADD = "poll.add_poll"  # Checked against meeting or org
    CHANGE = "poll.change_poll"
    DELETE = "poll.delete_poll"
    VIEW = "poll.view_poll"


class VotePermissions:
    """ Note that adding, deleting or changing a Vote is the same thing as being able to vote!
        Add is checked against a poll, and change/delete is checked against an existing vote.
        They should always yield the same result.
    """
    ADD = "vote.add_vote"
    CHANGE = "vote.change_vote"
    DELETE = "vote.delete_vote"
    VIEW = "vote.view_vote"
