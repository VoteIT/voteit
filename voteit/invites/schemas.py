from contextlib import contextmanager
from contextvars import ContextVar
from typing import List, TYPE_CHECKING

from pydantic import field_validator, StringConstraints, ConfigDict, BaseModel
from pydantic import ValidationInfo
from pydantic import Field

from voteit.core.validators import ensure_unique
from voteit.invites.utils import get_invite_adapter_registry
from voteit.messaging.base import AddedOrUpdatedSchema
from typing_extensions import Annotated

if TYPE_CHECKING:
    pass


class _SchemaContextSettings(BaseModel):
    limit: int | None = 1000


_inv_schema_vars = ContextVar("inv_schema_vars", default=_SchemaContextSettings())


@contextmanager
def schema_context(**kwargs):
    """
    Override defaults when checking schema
    """

    token = _inv_schema_vars.set(_SchemaContextSettings(**kwargs))
    try:
        yield
    finally:
        _inv_schema_vars.reset(token)


class RowColInvitesBaseSchema(BaseModel):
    r"""<- Note raw string for doctests here!
    >>> s = RowColInvitesBaseSchema

    Double empty should be okay
    >>> s(columns={'email'}, rows=[[''], ['hello@voteit.se'], ['']]).dict(include={'rows'})
    {'rows': [['hello@voteit.se']]}

    As text
    >>> s(columns={'email'}, rows="  \n \n hello@voteit.se \n \n ").dict(include={'rows'})
    {'rows': [['hello@voteit.se']]}

    With important data outside included columns
    >>> s(columns={'email'}, rows=[['', 'hello@voteit.se']])
    Traceback (most recent call last):
    ...
    pydantic.ValidationError: 1 validation error for RowColInvitesBaseSchema
        rows
    """

    columns: Annotated[
        List[
            Annotated[
                str,
                StringConstraints(
                    strip_whitespace=True,
                    to_lower=True,
                ),
            ]
        ],
        Field(
            max_length=20,
        ),
    ]
    rows: Annotated[
        List[
            Annotated[
                List[str | None | int],
                Field(
                    max_length=30,
                ),
            ]
        ],
        Field(),
    ]
    dryrun: bool = False  # Abort transaction when complete!

    @field_validator("columns")
    @classmethod
    def validate_columns_unique(cls, v: list[str]):
        # Uniqueness is enforced here rather than via conlist(unique_items=True)
        # so that it runs *after* constr() has stripped and lowercased -- the v1
        # form compared the raw input and so missed case/whitespace duplicates.
        return ensure_unique(v)

    @field_validator("columns")
    @classmethod
    def validate_columns_requirements(cls, v: list[str]):
        reg = get_invite_adapter_registry()
        reg.check_column_req(v)
        return v

    @field_validator("rows", mode="before")
    @classmethod
    def convert_rows(cls, v, info: ValidationInfo):
        if isinstance(v, str):
            v = v.splitlines()
        if isinstance(v, list):
            result = []
            for i, row in enumerate(v):
                if isinstance(row, str):
                    row = [x.strip() for x in row.split("\t")]
                    if any(row):
                        result.append(row)
                elif isinstance(row, list):
                    row = [x.strip() if isinstance(x, str) else x for x in row]
                    if any(row):
                        result.append(row)
                else:
                    raise ValueError(f"Got bogus value on row {i}: {row}")
            if "columns" not in info.data:
                raise ValueError(
                    "Couldn't validate rows because of invalid column names"
                )
            reg = get_invite_adapter_registry()
            reg.preflight(info.data["columns"], result)
            return result
        raise ValueError("Initial value of rows must be either string or list")

    @field_validator("rows")
    @classmethod
    def validate_rows_unique(cls, v: list[list]):
        for row in v:
            ensure_unique(row)
        return ensure_unique(v)

    @field_validator("rows")
    @classmethod
    def check_row_len(cls, v: list):
        """
        >>> v = list(range(5))
        >>> RowColInvitesBaseSchema.check_row_len(v)
        [0, 1, 2, 3, 4]
        >>> with schema_context(limit=2):
        ...     RowColInvitesBaseSchema.check_row_len(v)
        Traceback (most recent call last):
        ...
        ValueError: We only allow 2 rows to be added this way at one time
        >>> with schema_context(limit=None):
        ...     RowColInvitesBaseSchema.check_row_len(v)
        [0, 1, 2, 3, 4]

        # Default
        >>> RowColInvitesBaseSchema.check_row_len(list(range(1001)))
        Traceback (most recent call last):
        ...
        ValueError: We only allow 1000 rows to be added this way at one time

        """
        ctx = _inv_schema_vars.get()
        if ctx.limit and len(v) > ctx.limit:
            raise ValueError(
                f"We only allow {ctx.limit} rows to be added this way at one time"
            )
        return v

    @field_validator("rows")
    @classmethod
    def check_important_data_outside_read_columns(
        cls, v: list[list[str]], info: ValidationInfo
    ):
        col_len = len(info.data["columns"])
        bad_rows = []
        first_offender = None
        for i, row in enumerate(v):
            if any(row[col_len:]):
                if first_offender is None:
                    first_offender = row
                bad_rows.append(i)

        if bad_rows:
            msg = (
                f"You have rows that contain data that wouldn't be used since they have to many columns. "
                f"Example on line {bad_rows[0]} - with tabs replaced:\n'%s'\n"
                % "', '".join(first_offender)
            )
            if len(bad_rows) > 1:
                if len(bad_rows) > 5:
                    msg += f"\nThere are {len(bad_rows) - 1} other lines too - check your data."
                else:
                    msg += "\n%s are also too long" % ",".join(bad_rows[1:])
            raise ValueError(msg)
        return v

    @field_validator("rows")
    @classmethod
    def check_user_data_intersections(cls, v: list[list[str]], info: ValidationInfo):
        reg = get_invite_adapter_registry()
        reg.check_intersections(info.data["columns"], v)
        return v


class InvitesResultSchema(BaseModel):
    added: int = 0
    changed: int = 0
    existed: int = 0


class AnnotationResultSchema(InvitesResultSchema):
    # added, changed and existed should be used equally for registered
    # users and users who haven't used an invitation yet.
    name: str
    msg: str | None = None
    # Progress
    curr: int | None = None
    total: int | None = None
    # Any invite that got a new annotation - ie we might want to send InviteChanged message with has_annotations
    newly_annotated_invites: list[int] = Field(default_factory=list)


class InviteDataTypesSchema(BaseModel):
    name: str
    title: str
    is_user_data: bool
    is_annotation: bool
    is_clearable: bool
    is_runnable: bool

    @field_validator("title", mode="before")
    @classmethod
    def translate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class InviteAddedOrUpdatedSchema(AddedOrUpdatedSchema):
    user_data: dict
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    @field_validator("user_data")
    @classmethod
    def mask_sensitive(cls, v: dict):
        """
        >>> InviteAddedOrUpdatedSchema(pk=1, user_data={'email': 'jane@voteit.se', 'swedish_ssn': '191212121212'})
        InviteAddedOrUpdatedSchema(pk=1, user_data={'email': 'jane@voteit.se', 'swedish_ssn': '19121212'})
        """
        reg = get_invite_adapter_registry()
        return reg.get_masked_user_data(v)
