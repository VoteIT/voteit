from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from pydantic import conint
from pydantic import constr
from pydantic.main import BaseModel

from voteit.invites.abcs import InviteDataAdapter
from voteit.invites.registries import invite_adapter_registry


class GroupSchema(BaseModel):
    group: constr(to_lower=True, strip_whitespace=True, max_length=100)


@invite_adapter_registry
class Group(InviteDataAdapter):
    """
    >>> data = [['WooOO'], [' '], ['  Important']]
    >>> Group.preflight([Group.name], data)
    >>> data
    [['woooo'], [''], ['important']]
    """

    name = "group"
    schema = GroupSchema
    title = _("GroupID")
