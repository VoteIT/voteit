from typing import TYPE_CHECKING

from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import Field
from pydantic import conlist
from pydantic import constr
from pydantic import root_validator
from pydantic import validator

from voteit.core.validators import root_validate_roles_and_model
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.workflows import InviteWf

if TYPE_CHECKING:
    from voteit.invites.abcs import InviteDataAdapter


# class CombinedInviteSchema(BaseModel):
#     """
#     This will be combined with other validation schemas. But they must exist.
#     >>> CombinedInviteSchema(one=1)
#     Traceback (most recent call last):
#     ...
#     pydantic.error_wrappers.ValidationError: 1 validation error for CombinedInviteSchema
#     __root__
#       At least one value required (type=value_error)
#     """
#
#     @root_validator
#     def at_least_one(cls, values: dict):
#         reg = get_invite_adapter_registry()
#         ud_keys = reg.user_data_keys
#         for k, v in values.items():
#             if v and k in ud_keys:
#                 return values
#         raise ValueError("At least one user_data value required")


class InvitesMetaMixinSchema(BaseModel):
    roles: conlist(
        constr(
            strip_whitespace=True,
            to_lower=True,
        ),
        unique_items=True,
        max_items=5,
    )
    skip_states: conlist(
        constr(
            strip_whitespace=True,
            to_lower=True,
        ),
        unique_items=True,
        max_items=5,
    ) = [InviteWf.REJECTED]
    meeting: int

    @validator("roles")
    def validate_roles(cls, v):
        root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v

    @validator("skip_states")
    def validate_skip_states(cls, v: list[str]):
        for item in v:
            if item not in InviteWf.states:
                raise ValueError(
                    f"{item} is not a valid workflow state for MeetingInvite"
                )
        return v


class AddTypedInvitesSchema(InvitesMetaMixinSchema):
    r"""<- Note raw string for doctests here!

    >>> AddTypedInvitesSchema.__fields__.keys()
    dict_keys(['roles', 'skip_states', 'meeting', 'type', 'user_data'])

    Single line
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['hello@betahaus.net'], meeting=1).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'user_data': ['hello@betahaus.net']}

    Caps
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['HELLO@betahaus.net'], meeting=1).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'user_data': ['hello@betahaus.net']}

    Str
    >>> AddTypedInvitesSchema(user_data='HELLO@betahaus.net\nhi@betahaus.net', meeting=1, roles=['participant']).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'user_data': ['hello@betahaus.net', 'hi@betahaus.net']}


    Blankspace should be skipped or trimmed
    >>> AddTypedInvitesSchema(roles=['participant'], \
    ... user_data=['', '    WoHo@betahaus.net', ' '], meeting=1).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'user_data': ['woho@betahaus.net']}

    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['bad_email'], meeting=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    No real data
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['  ', ''], meeting=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=None, meeting=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> AddTypedInvitesSchema(user_data=['duplicate@betahaus.net', 'duplicate@betahaus.net'],\
    ... meeting=1, roles=['participant'])
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for AddTypedInvitesSchema
    user_data
      The following rows contain values that were already added above that row. That would cause several invites to match the same data. Rows: 2
    The duplicate values are: duplicate@betahaus.net (type=value_error)
    """

    type: str = "email"
    user_data: conlist(
        constr(strip_whitespace=True),
        unique_items=True,
        max_items=1000,
    )

    @validator("type")
    def validate_type(cls, v: str):
        if v not in get_invite_adapter_registry():
            raise ValueError(f"{v} is not a valid type")
        return v

    @validator("user_data", pre=True)
    def convert_user_data(cls, v: str):
        if isinstance(v, str):
            return v.splitlines()
        return v

    @validator("user_data")
    def validate_user_data(cls, v: list | str, values: dict):
        reg = get_invite_adapter_registry()
        # Delegate all validation to the registry
        invite_type = values.get("type")
        if not invite_type:
            raise ValueError("No type specified")
        adapter: InviteDataAdapter = reg[invite_type]
        results = []
        i = 1
        schema_fail_row = set()
        for item in v:
            if item:
                try:
                    inst = adapter.schema(
                        **{invite_type: item}
                    )  # Might raise pydantics ValidationError
                except ValueError:
                    schema_fail_row.add(i)
                    continue
                results.append(getattr(inst, invite_type))
            i += 1
        if schema_fail_row:
            raise ValueError(
                _(
                    "The following rows don't match type %(title)s: %(rownums)s"
                    % {
                        "title": str(adapter.title),
                        "rownums": ", ".join(str(x) for x in sorted(schema_fail_row)),
                    }
                )
            )
        if not results:
            raise ValueError("user_data required")
        return results


class AddAnnotatedInvitesSchema(InvitesMetaMixinSchema):
    r"""<- Note raw string for doctests here!

    Initial validation before touching the db. Very basic checks.
    The structure will be transformed later on to relevant data structure.

    >>> base_qs = {'meeting': 1, 'roles': ['participant']}

    Single line
    >>> AddAnnotatedInvitesSchema(columns=['email'], rows=[["one@betahaus.net"], ["two@betahaus.net"]], **base_qs).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'columns': ['email'], 'rows': [['one@betahaus.net'], ['two@betahaus.net']]}

    Strip whitespace - but we don't convert caps
    >>> AddAnnotatedInvitesSchema(columns=['email'], rows="one@betahaus.net   \n   tWo@betahaus.net", **base_qs).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'columns': ['email'], 'rows': [['one@betahaus.net'], ['tWo@betahaus.net']]}

    Strip shouldn't mess up validators
    >>> AddAnnotatedInvitesSchema(columns=['email'], rows="one@betahaus.net   \n   one@betahaus.net", **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for AddAnnotatedInvitesSchema
    rows
      the list has duplicated items (type=value_error.list.unique_items)
    """

    columns: conlist(
        constr(
            strip_whitespace=True,
            to_lower=True,
        ),
        unique_items=True,
        max_items=20,
    )
    # Important note! unique_items doesn't work when constr changes data. Rows must be altered before
    rows: conlist(
        conlist(
            str,
            unique_items=True,
            max_items=30,
        ),
        unique_items=True,
        max_items=1000,
    )

    @validator("rows", pre=True)
    def convert_rows(cls, v):
        if isinstance(v, str):
            result = []
            for row in v.splitlines():
                result.append(row.split("\t"))
            v = result
        if isinstance(v, list):
            result = []
            for row in v:
                result.append([x.strip() for x in row])
            return result
        return v

    @validator("columns", each_item=True)
    def validate_columns(cls, v: str):
        reg = get_invite_adapter_registry()
        if v in reg:
            return v
        raise ValueError(f"{v} is not a valid column name")

    @validator("rows")
    def check_row_len(cls, v: list[list[str]], values: dict):
        col_len = len(values["columns"])
        i = 1
        too_long = []
        for row in v:
            if len(row) > col_len:
                too_long.append(i)
            i += 1
        if too_long:
            raise ValueError(
                f"The following rows have more columns than they should have: {too_long[:10]}"
            )
        return v
