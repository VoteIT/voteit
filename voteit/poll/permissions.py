from voteit.core.permission import ModelPermissions
from voteit.core.permission import Permission as P


class PollPermissions(ModelPermissions):
    model = "poll"
    ADD = P("poll.add_poll", context="agenda_item")
    CHANGE = P("poll.change_poll")
    DELETE = P("poll.delete_poll")
    VIEW = P("poll.view_poll")


class VotePermissions(ModelPermissions):
    model = "vote"
    ADD = P("poll.add_vote", context="poll")
    CHANGE = P("poll.change_vote", "poll.Vote")
    DELETE = P("poll.delete_vote", "poll.Vote")
    VIEW = P("poll.view_vote", "poll.Vote")


class ElectoralRegisterPermissions(ModelPermissions):
    model = "electoral_register"
    VIEW = P("poll.view_electoralregister")
