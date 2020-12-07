from voteit.core.registries import permissions


class MeetingPermissions:
    ADD = permissions.create("meeting.add_meeting", "organisation.Organisation")
    CHANGE = permissions.create("meeting.change_meeting", "meeting.Meeting")
    DELETE = permissions.create("meeting.delete_meeting", "meeting.Meeting")
    VIEW = permissions.create("meeting.view_meeting", "meeting.Meeting")
    MODERATE = permissions.create("meeting.moderate_meeting", "meeting.Meeting")
    ARCHIVE = permissions.create("meeting.archive_meeting", "meeting.Meeting")
