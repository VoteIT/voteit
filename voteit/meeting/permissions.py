from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class MeetingPermissions(ModelPermissions):
    model = "meeting"

    ADD = P("meeting.add_meeting", context="organisation")
    CHANGE = P("meeting.change_meeting")
    CHANGE_DIALECT = P("meeting.change_dialect_meeting")
    DELETE = P("meeting.delete_meeting")
    VIEW = P("meeting.view_meeting")
    LIST = P("meeting.list_meeting")  # Include basic meeting details in listings
    MODERATE = P("meeting.moderate_meeting")
    ARCHIVE = P("meeting.archive_meeting")
    CHANGE_ROLES = P("meeting.change_roles_meeting")
    VIEW_ROLES = P("meeting.view_roles_meeting")


class MeetingGroupPermissions(ModelPermissions):
    model = "meeting_group"

    ADD = P("meeting.add_meetinggroup", context="meeting")
    CHANGE = P("meeting.change_meetinggroup")
    DELETE = P("meeting.delete_meetinggroup")
    VIEW = P("meeting.view_meetinggroup")
