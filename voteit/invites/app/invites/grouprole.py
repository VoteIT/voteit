from __future__ import annotations
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import constr

from voteit.invites.abcs import AnnotationDataAdapter
from voteit.invites.app.invites.group import InviteGroup
from voteit.invites.registries import invite_adapter_registry

if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import Meeting


class GroupRoleSchema(BaseModel):
    grouprole: constr(to_lower=True, strip_whitespace=True, max_length=100)


@invite_adapter_registry
class InviteGroupRole(AnnotationDataAdapter):
    """
    >>> data = [['WooOO'], [' '], ['  Important']]
    >>> InviteGroupRole.preflight([InviteGroupRole.name], data)
    >>> data
    [['woooo'], [''], ['important']]
    """

    name = "grouprole"
    schema = GroupRoleSchema
    title = _("Group role")
    is_runnable = False

    @classmethod
    def check_column_req(cls, columns: list[str]):
        """
        >>> InviteGroupRole.check_column_req(['boo'])
        >>> InviteGroupRole.check_column_req(['boo', InviteGroup.name, InviteGroupRole.name, InviteGroup.name, InviteGroupRole.name])
        >>> InviteGroupRole.check_column_req(['boo', InviteGroupRole.name])
        Traceback (most recent call last):
        ...
        ValueError: GroupRole requires the column left of it to be group
        >>> InviteGroupRole.check_column_req([InviteGroupRole.name])
        Traceback (most recent call last):
        ...
        ValueError: GroupRole requires the column left of it to be group
        """
        for i in cls.get_colidx(columns):
            if columns[i - 1] != InviteGroup.name:
                raise ValueError("GroupRole requires the column left of it to be group")

    @classmethod
    def validate(
        cls, *, columns: list[str], rows: list[list[str | None | int]], meeting: Meeting
    ):
        values = cls.get_row_values(columns, rows)
        missing = values - set(
            meeting.group_roles.filter(role_id__in=values).values_list(
                "role_id", flat=True
            )
        )
        if missing:
            raise ValueError(
                "The following role_ids don't exist: %s" % ",".join(missing)
            )

    def accepted(self):
        """
        Not needed here since group will take care of the same thing
        """

    @classmethod
    def annotate(cls, **kwargs):
        """
        Delegated to group since it handles the same data
        """

    @classmethod
    def clear(cls, meeting):
        """
        Handled by GroupID
        """
        return MeetingInvite.objects.none()
