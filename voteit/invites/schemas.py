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


class CombinedInviteSchema(BaseModel):
    """
    This will be combined with other validation schemas. But they must exist.
    >>> CombinedInviteSchema(one=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for CombinedInviteSchema
    __root__
      At least one value required (type=value_error)
    """

    @root_validator
    def at_least_one(cls, values: dict):
        for v in values.values():
            if v:
                return values
        raise ValueError("At least one value required")


class AddTypedInvitesSchema(BaseModel):
    r"""<- Note raw string for doctests here!

    >>> AddTypedInvitesSchema.__fields__.keys()
    dict_keys(['roles', 'model', 'skip_states', 'type', 'user_data', 'meeting'])

    Single line
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['hello@betahaus.net'], meeting=1).dict(exclude_unset=True)
    {'roles': ['participant'], 'user_data': ['hello@betahaus.net'], 'meeting': 1}

    Caps
    >>> AddTypedInvitesSchema(roles=['participant'], user_data=['HELLO@betahaus.net'], meeting=1).dict(exclude_unset=True)
    {'roles': ['participant'], 'user_data': ['hello@betahaus.net'], 'meeting': 1}

    Str
    >>> AddTypedInvitesSchema(user_data='HELLO@betahaus.net\nhi@betahaus.net', meeting=1, roles=['participant']).dict(exclude_unset=True)
    {'roles': ['participant'], 'user_data': ['hello@betahaus.net', 'hi@betahaus.net'], 'meeting': 1}


    Blankspace should be skipped or trimmed
    >>> AddTypedInvitesSchema(roles=['participant'], \
    ... user_data=['', '    WoHo@betahaus.net', ' '], meeting=1).dict(exclude_unset=True)
    {'roles': ['participant'], 'user_data': ['woho@betahaus.net'], 'meeting': 1}

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

    roles: list[str]
    model: str = Field("meeting", const=True)  # Constant
    skip_states: set[str] = {InviteWf.REJECTED}
    type: str = "email"
    user_data: conlist(
        constr(strip_whitespace=True),
        unique_items=True,
        max_items=1000,
    )
    meeting: int
    # Validators
    _check_roles = root_validator(skip_on_failure=True, allow_reuse=True)(
        root_validate_roles_and_model
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
