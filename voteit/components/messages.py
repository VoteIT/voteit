from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingComponentAdded(BaseObjectAdded):
    name = "meeting_component.added"


@outgoing
class MeetingComponentChanged(BaseObjectChanged):
    name = "meeting_component.changed"


@outgoing
class MeetingComponentDeleted(BaseObjectDeleted):
    name = "meeting_component.deleted"


@outgoing
class OrganisationComponentAdded(BaseObjectAdded):
    name = "organisation_component.added"


@outgoing
class OrganisationComponentChanged(BaseObjectChanged):
    name = "organisation_component.changed"


@outgoing
class OrganisationComponentDeleted(BaseObjectDeleted):
    name = "organisation_component.deleted"
