# from typing import TYPE_CHECKING
from typing import Union

from rules import Predicate
from typing import Type
from django.db.models import Model

from voteit.core.component import Registry
from voteit.core.permission import PermissionRegistry

from voteit.core.permission import Permission
from voteit.core.predicate import PredicateRegistry


class ContentRegistry(Registry):
    """Stores content types and handles naming.
    Any model that's ready should be present here

    >>> content_types["meeting"]
    <class 'voteit.meeting.models.Meeting'>

    Natural key can be looked up via this registry too
    By str
    >>> content_types.get_natural_key("agenda_item")
    'agenda.agendaitem'

    By instance or class
    >>> from voteit.meeting.models import Meeting
    >>> content_types.get_natural_key(Meeting)
    'meeting.meeting'
    >>> content_types.get_natural_key(Meeting())
    'meeting.meeting'

    We've also added the User method here as user regardless of where it comes from
    >>> from django.contrib.auth import get_user_model
    >>> User = get_user_model()
    >>> "user" in content_types
    True
    >>> content_types["user"] is User
    True
    """

    def get_natural_key(self, obj: Union[str, Model, Type[Model]]) -> str:
        if isinstance(obj, str):
            obj = self[obj]
        if isinstance(obj, Model):
            obj = obj.__class__
        return f"{obj._meta.app_label}.{obj._meta.model_name.lower()}"


predicates = PredicateRegistry(Predicate)
permissions = PermissionRegistry(Permission)
content_types = ContentRegistry(Model)
