from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import StringConstraints
from pydantic import field_validator
from typing_extensions import Annotated

from voteit.invites.abcs import InviteUserDataAdapter
from voteit.invites.registries import invite_adapter_registry


class MemberIdSchema(BaseModel):
    member_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]

    @field_validator("member_id", mode="before")
    @classmethod
    def from_number(cls, v):
        # Spreadsheets hand over numeric cells as numbers
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v)
        return v


@invite_adapter_registry
class InviteMemberId(InviteUserDataAdapter):
    """
    A member id, as vouched for by a backend that sets ``MEMBER_ID_KEY``.
    See ``voteit.organisation.utils.get_user_member_ids``.

    >>> rows = [[' 123456 '], [987]]
    >>> InviteMemberId.preflight(['member_id'], rows)
    >>> rows
    [['123456'], ['987']]

    >>> InviteMemberId.preflight(['member_id'], [['x' * 51]])
    Traceback (most recent call last):
    ...
    voteit.invites.exceptions.DataColValidationError: Column member_id (1) validation failed at rows: [1]
    """

    name = "member_id"
    schema = MemberIdSchema
    title = _("Member id")
