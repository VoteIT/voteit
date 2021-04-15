from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class MeetingPermissions(ModelPermissions):
    model = "meeting"

    ADD = P("meeting.add_meeting", context="organisation")
    CHANGE = P("meeting.change_meeting")
    DELETE = P("meeting.delete_meeting")
    VIEW = P("meeting.view_meeting")
    MODERATE = P("meeting.moderate_meeting")
    ARCHIVE = P("meeting.archive_meeting")
    CHANGE_ROLES = P("meeting.change_roles_meeting")
    VIEW_ROLES = P("meeting.view_roles_meeting")
