from typing import TYPE_CHECKING

from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import Field
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from voteit.core.validators import root_validate_roles_and_model
from voteit.invites.utils import get_invite_adapter_registry

if TYPE_CHECKING:
    from voteit.invites.abcs import InviteDataAdapter


class InvitesMetaMixinSchema(BaseModel):
    roles: conlist(
        constr(
            strip_whitespace=True,
            to_lower=True,
        ),
        unique_items=True,
        max_items=5,
    )
    meeting: int

    @validator("roles")
    def validate_roles(cls, v):
        root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v


class RowColInvitesBaseSchema(BaseModel):
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
            str | None | int,
            unique_items=True,
            max_items=30,
        ),
        unique_items=True,
        max_items=1000,
    )
    dryrun: bool = False  # Abort transaction when complete!

    @validator("columns")
    def validate_columns_requirements(cls, v: list[str]):
        reg = get_invite_adapter_registry()
        reg.check_column_req(v)
        return v

    @validator("rows", pre=True)
    def convert_rows(cls, v, values: dict):
        if isinstance(v, str):
            v = v.splitlines()
        if isinstance(v, list):
            result = []
            for i, row in enumerate(v):
                if isinstance(row, str):
                    result.append([x.strip() for x in row.split("\t")])
                elif isinstance(row, list):
                    result.append([x.strip() if isinstance(x, str) else x for x in row])
                else:
                    raise ValueError(f"Got bogus value on row {i}: {row}")
            if "columns" not in values:
                raise ValueError(
                    "Couldn't validate rows because of invalid column names"
                )
            reg = get_invite_adapter_registry()
            reg.preflight(values["columns"], result)
            return result
        raise ValueError("Initial value of rows must be either string or list")

    @validator("rows")
    def check_user_data_intersections(cls, v: list[list[str]], values: dict):
        reg = get_invite_adapter_registry()
        reg.check_intersections(values["columns"], v)
        return v


class AddMixedUserDataInvitesSchema(RowColInvitesBaseSchema, InvitesMetaMixinSchema):
    r"""<- Note raw string for doctests here!

    Initial validation before touching the db. Very basic checks.
    The structure will be transformed later on to relevant data structure.

    >>> base_qs = {'meeting': 1, 'roles': ['participant']}

    Single line
    >>> AddMixedUserDataInvitesSchema(columns=['email'], rows=[["one@betahaus.net"], ["two@betahaus.net"]], **base_qs).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'columns': ['email'], 'rows': [['one@betahaus.net'], ['two@betahaus.net']]}

    Strip whitespace - preflight handles other conversions
    >>> AddMixedUserDataInvitesSchema(columns=['email'], rows="one@betahaus.net   \n   tWo@betahaus.net", **base_qs).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'columns': ['email'], 'rows': [['one@betahaus.net'], ['two@betahaus.net']]}

    Multivals
    >>> AddMixedUserDataInvitesSchema(columns=['email', 'swedish_ssn'], rows=[['a@boo.com', '121212-1212'],['b@boo.com', '20200101-2398']], **base_qs).dict(exclude_unset=True, exclude={'meeting', 'roles'})
    {'columns': ['email', 'swedish_ssn'], 'rows': [['a@boo.com', '201212121212'], ['b@boo.com', '202001012398']]}

    Rows must be unique, and case-handling shouldn't mess that up
    >>> AddMixedUserDataInvitesSchema(columns=['email'], rows="one@betahaus.net   \n   ONe@betahaus.net", **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for AddAnnotatedInvitesSchema
    rows
      the list has duplicated items (type=value_error.list.unique_items)

    Strip shouldn't mess up validators
    >>> AddMixedUserDataInvitesSchema(columns=['email'], rows="one@betahaus.net   \n   one@betahaus.net", **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for AddAnnotatedInvitesSchema
    rows
      the list has duplicated items (type=value_error.list.unique_items)

    Invites with intersections are problematic too, so we'll block those
    >>> AddMixedUserDataInvitesSchema(columns=['email', 'swedish_ssn'], rows=[['a@boo.com', '121212-1212'],['a@boo.com']], **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for AddAnnotatedInvitesSchema
    rows
      The value email=a@boo.com is used within different subsets of user data. Offending row: 1 (type=value_error)

    And a problematic mix
    >>> AddMixedUserDataInvitesSchema(columns=['email', 'swedish_ssn'], rows=[['a@boo.com', '121212-1212'],['a@boo.com', '20200101-2398']], **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 2 validation error for AddAnnotatedInvitesSchema
    rows
      The value email=a@boo.com is used within different subsets of user data. Offending row: 1 (type=value_error)

    Bad column name
    >>> AddMixedUserDataInvitesSchema(columns=['bad'], rows=[['123']], **base_qs)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 2 validation errors for AddMixedUserDataInvitesSchema
    columns
      bad is not a valid column (type=value_error)
    rows
      Couldn't validate rows because of invalid column names (type=value_error)
    """


class AddInviteAnnotationsSchema(RowColInvitesBaseSchema):
    meeting: int


class InvitesResultSchema(BaseModel):
    added: int = 0
    changed: int = 0
    existed: int = 0


class AnnotationResultSchema(InvitesResultSchema):
    # added, changed and existed should be used equally for registered
    # users and users who haven't used an invitation yet.
    name: str
    msg: str | None
    # Any invite that got a new annotation - ie we might want to send InviteChanged message with has_annotations
    newly_annotated_invites: list[int] = Field(default_factory=list)


class InviteDataTypesSchema(BaseModel):
    name: str
    title: str
    is_user_data: bool
    is_annotation: bool
    is_clearable: bool

    @validator("title", pre=True)
    def translate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    class Config:
        orm_mode = True


class ClearInviteAnnotationsSchema(BaseModel):
    """
    >>> ClearInviteAnnotationsSchema(meeting=1, types=['group'])
    ClearInviteAnnotationsSchema(meeting=1, types=['group'])
    >>> ClearInviteAnnotationsSchema(meeting=1, types=['404'])
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for ClearInviteAnnotationsSchema
    types
      404 is not an invite annotation adapter (type=value_error)
    >>> ClearInviteAnnotationsSchema(meeting=1, types=['grouprole'])
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for ClearInviteAnnotationsSchema
    types
      grouprole can not be cleared (type=value_error)
    """

    meeting: int
    types: conlist(
        constr(strip_whitespace=True, to_lower=True), unique_items=True, min_items=1
    )

    @validator("types")
    def validate_types(cls, v: list[str]):
        reg = get_invite_adapter_registry()
        for k in v:
            if k not in reg:
                raise ValueError("No such invite adapter")
            if not reg[k].is_annotation:
                raise ValueError(f"{k} is not an invite annotation adapter")
            if not reg[k].is_clearable:
                raise ValueError(f"{k} can not be cleared")
        return v
