from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class MeetingInvitePermissions(ModelPermissions):
    model = "meeting_invite"
    ADD = P("invites.add_meetinginvite", context="meeting")
    CHANGE = P("invites.change_meetinginvite")
    DELETE = P("invites.delete_meetinginvite")
    VIEW = P("invites.view_meetinginvite", context={"meeting_invite", "meeting"})
