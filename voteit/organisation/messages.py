from typing import Literal
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import ObjectAddedOrChanged


@outgoing
class OrganisationChanged(ObjectAddedOrChanged):
    action: Literal["organisation.changed"] = "organisation.changed"
