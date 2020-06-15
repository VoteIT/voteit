

class PollPermissions:
    ADD = "voteit.poll.add_poll"  # Checked against meeting or org
    CHANGE = "voteit.poll.change_poll"
    DELETE = "voteit.poll.delete_poll"
    VIEW = "voteit.poll.view_poll"


class VotePermissions:
    """ Note that adding, deleting or changing a Vote is the same thing as being able to vote!
        Add is checked against a poll, and change/delete is checked against an existing vote.
        They should always yield the same result.
    """
    ADD = "voteit.poll.add_vote"
    CHANGE = "voteit.poll.change_vote"
    DELETE = "voteit.poll.delete_vote"
    VIEW = "voteit.poll.view_vote"
