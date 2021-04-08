from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class MeetingInvitePermissions(ModelPermissions):
    model = "meeting_invite"
    ADD = P("access_policy.add_meetinginvite", context="meeting")
    CHANGE = P("access_policy.change_meetinginvite")
    DELETE = P("access_policy.delete_meetinginvite")
    VIEW = P("access_policy.view_meetinginvite")
