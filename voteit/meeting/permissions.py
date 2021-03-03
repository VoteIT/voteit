from voteit.core.registries import permissions


class MeetingPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.meeting.models import Meeting
    >>> find_bad_permission_names(MeetingPermissions, Meeting)

    """

    ADD = permissions.create("meeting.add_meeting", "organisation.Organisation")
    CHANGE = permissions.create("meeting.change_meeting", "meeting.Meeting")
    DELETE = permissions.create("meeting.delete_meeting", "meeting.Meeting")
    VIEW = permissions.create("meeting.view_meeting", "meeting.Meeting")
    MODERATE = permissions.create("meeting.moderate_meeting", "meeting.Meeting")
    ARCHIVE = permissions.create("meeting.archive_meeting", "meeting.Meeting")
    ADD_ROLES = permissions.create("meeting.add_roles_meeting", "meeting.Meeting")
    REMOVE_ROLES = permissions.create("meeting.remove_roles_meeting", "meeting.Meeting")
