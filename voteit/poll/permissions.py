from voteit.core.registries import permissions


class PollPermissions:
    ADD = permissions.create("poll.add_poll", "agenda.AgendaItem")
    CHANGE = permissions.create("poll.change_poll", "poll.Poll")
    DELETE = permissions.create("poll.delete_poll", "poll.Poll")
    VIEW = permissions.create("poll.view_poll", "poll.Poll")


class VotePermissions:
    """ Note that adding, deleting or changing a Vote is the same thing as being able to vote!
        Add is checked against a poll, and change/delete is checked against an existing vote.
        They should always yield the same result.
    """
    ADD = permissions.create("vote.add_vote", "poll.Poll")
    CHANGE = permissions.create("vote.change_vote", "poll.Vote")
    DELETE = permissions.create("vote.delete_vote", "poll.Vote")
    VIEW = permissions.create("vote.view_vote", "poll.Vote")
