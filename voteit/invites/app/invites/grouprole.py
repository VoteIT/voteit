from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import constr

from voteit.invites.abcs import InviteDataAdapter
from voteit.invites.app.invites.group import Group
from voteit.invites.registries import invite_adapter_registry


class GroupRoleSchema(BaseModel):
    grouprole: constr(to_lower=True, strip_whitespace=True, max_length=100)


@invite_adapter_registry
class GroupRole(InviteDataAdapter):
    """
    >>> data = [['WooOO'], [' '], ['  Important']]
    >>> GroupRole.preflight([GroupRole.name], data)
    >>> data
    [['woooo'], [''], ['important']]
    """

    name = "grouprole"
    schema = GroupRoleSchema
    title = _("Group role")

    @classmethod
    def check_column_req(cls, columns: list[str]):
        """
        >>> GroupRole.check_column_req(['boo'])
        >>> GroupRole.check_column_req(['boo', Group.name, GroupRole.name, Group.name, GroupRole.name])
        >>> GroupRole.check_column_req(['boo', GroupRole.name])
        Traceback (most recent call last):
        ...
        ValueError: GroupRole requires the column left of it to be group
        >>> GroupRole.check_column_req([GroupRole.name])
        Traceback (most recent call last):
        ...
        ValueError: GroupRole requires the column left of it to be group
        """
        for i in cls.get_colidx(columns):
            if columns[i - 1] != Group.name:
                raise ValueError("GroupRole requires the column left of it to be group")
