from pydantic import BaseModel
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from voteit.components.utils import get_meeting_component_adapters
from voteit.core.validators import root_validate_roles_and_model


class GroupRoleSchema(BaseModel):
    title: constr(max_length=100)
    role_id: constr(max_length=100, to_lower=True)
    roles: list[str] = ()
    can_propose_as: bool = False
    can_discuss_as: bool = False

    @validator("roles")
    def validate_roles(cls, v):
        root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v


class GroupSchema(BaseModel):
    title: constr(max_length=100) | None
    groupid: constr(max_length=100, to_lower=True, strip_whitespace=True)


class ComponentSettings(BaseModel):
    """
    >>> ComponentSettings(name='404')
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for ComponentSettings
    >>> from voteit.components.app.components.proposal_print import ProposalPrint
    >>> ComponentSettings(name=ProposalPrint.name)
    ComponentSettings(name='proposal_print', settings=None)
    >>> from voteit.components.app.components.message import FlashMessage
    >>> ComponentSettings(name=FlashMessage.name, settings={'msg': 'Hello'})
    ComponentSettings(name='flash_message', settings={'msg': 'Hello'})
    >>> ComponentSettings(name=FlashMessage.name)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for ComponentSettings
    >>> ComponentSettings(name=FlashMessage.name, settings={'just': 'wrong'})
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for ComponentSettings
    """

    name: constr(strip_whitespace=True, to_lower=True)
    settings: dict | None = None

    @validator("name")
    def validate_name(cls, v: str):
        if v not in get_meeting_component_adapters():
            raise ValueError(f"{v} is not a meeting component name")
        return v

    @validator("settings", always=True)
    def validate_settings(cls, v, values):
        try:
            adapter = get_meeting_component_adapters()[values["name"]]
        except KeyError:
            return  # Will be caught by other validator
        if adapter.schema is not None:
            if not isinstance(v, dict):
                raise ValueError("missing or isn't a dict")
            adapter.schema(**v)
        return v


class DialectSchema(BaseModel):
    """
    Settings for a meeting dialect

    >>> data={'title': 'Test', 'name': 'test',\
        'roles': [{'title': 'Supervisor', 'role_id': 'supervisor', 'roles': ['discusser', 'proposer']}],\
        'groups': [{'title': 'Board', 'groupid': 'board'}], 'er_policy_name': 'auto_before_poll',\
        'group_votes_active': True, 'group_roles_active': True}
    >>> _ = DialectSchema(**data)
    >>> bad_roles=data.copy()
    >>> bad_roles['roles'] = [{'title': 'Bad', 'roles': ['boho']}]
    >>> DialectSchema(**bad_roles)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    >>> _ = DialectSchema(block_roles=[], **data)
    >>> DialectSchema(block_roles=['jeff'], **data)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    title: str
    description: str = ""
    name: str
    roles: conlist(GroupRoleSchema, unique_items=True) = []
    groups: conlist(GroupSchema, unique_items=True) = []
    er_policy_name: str | None = None
    group_votes_active: bool | None = None
    group_roles_active: bool | None = None
    groups_can_delegate: bool = (
        False  # Can groups delegate their vote to another group?
    )
    proposal_id_policy_name: str | None = None
    installable: bool = True  # Offer as selection for all organisations?
    requires: conlist(
        constr(to_lower=True, strip_whitespace=True),
        unique_items=True,
    ) = []
    view_components: dict[str, str] = {}
    configure_components: list[ComponentSettings] = []
    block_components: conlist(
        constr(to_lower=True, strip_whitespace=True),
        unique_items=True,
    ) = []
    block_roles: conlist(
        constr(to_lower=True, strip_whitespace=True),
        unique_items=True,
    ) = []
    run_scripts: conlist(
        constr(strip_whitespace=True),
        unique_items=True,
    ) = []

    @validator("block_roles")
    def validate_roles(cls, v):
        if v:
            root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v
