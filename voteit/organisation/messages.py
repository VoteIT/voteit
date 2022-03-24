from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectChanged


@outgoing
class OrganisationChanged(BaseObjectChanged):
    name = "organisation.changed"
