from voteit.core.registries import permissions


class PollPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.poll.models import Poll
    >>> find_bad_permission_names(PollPermissions, Poll)

    """

    ADD = permissions.create("poll.add_poll", "agenda.AgendaItem")
    CHANGE = permissions.create("poll.change_poll", "poll.Poll")
    DELETE = permissions.create("poll.delete_poll", "poll.Poll")
    VIEW = permissions.create("poll.view_poll", "poll.Poll")


class VotePermissions:
    """Note that adding, deleting or changing a Vote is the same thing as being able to vote!
        Add is checked against a poll, and change/delete is checked against an existing vote.
        They should always yield the same result.

    The permissions must map the object permissions in django.
    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.poll.models import Vote
    >>> find_bad_permission_names(VotePermissions, Vote)

    """

    ADD = permissions.create("poll.add_vote", "poll.Poll")
    CHANGE = permissions.create("poll.change_vote", "poll.Vote")
    DELETE = permissions.create("poll.delete_vote", "poll.Vote")
    VIEW = permissions.create("poll.view_vote", "poll.Vote")
