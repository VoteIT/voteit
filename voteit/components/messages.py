from typing import Literal
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingComponentChanged(ObjectAddedOrChanged):
    action: Literal["meeting_component.changed"] = "meeting_component.changed"


@outgoing
class MeetingComponentDeleted(ObjectDeleted):
    action: Literal["meeting_component.deleted"] = "meeting_component.deleted"


@outgoing
class OrganisationComponentChanged(ObjectAddedOrChanged):
    action: Literal["organisation_component.changed"] = "organisation_component.changed"


@outgoing
class OrganisationComponentDeleted(ObjectDeleted):
    action: Literal["organisation_component.deleted"] = "organisation_component.deleted"
