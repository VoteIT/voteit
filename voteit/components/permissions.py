from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class MeetingComponentPermissions(ModelPermissions):
    model = "meeting_component"

    ADD = P("components.add_meetingcomponent", context="meeting")
    CHANGE = P("components.change_meetingcomponent")
    DELETE = P("components.delete_meetingcomponent")
    VIEW = P("components.view_meetingcomponent")


class OrganisationComponentPermissions(ModelPermissions):
    model = "organisation_component"

    ADD = P("components.add_organisationcomponent", context="organisation")
    CHANGE = P("components.change_organisationcomponent")
    DELETE = P("components.delete_organisationcomponent")
    VIEW = P("components.view_organisationcomponent")
