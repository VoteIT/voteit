from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class PollPermissions(ModelPermissions):
    model = "poll"
    ADD = P("poll.add_poll", context={"agenda_item", "meeting"})
    CHANGE = P("poll.change_poll")
    DELETE = P("poll.delete_poll")
    VIEW = P("poll.view_poll")
    CHANGE_STATE = P("poll.change_state_poll")


class VotePermissions(ModelPermissions):
    model = "vote"
    ADD = P("poll.add_vote", context="poll")
    CHANGE = P("poll.change_vote")
    DELETE = P("poll.delete_vote")
    VIEW = P("poll.view_vote")


class ElectoralRegisterPermissions(ModelPermissions):
    model = "electoral_register"
    ADD = P("poll.add_electoralregister", context="meeting")
    VIEW = P("poll.view_electoralregister")
