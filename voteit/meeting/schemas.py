from pydantic import BaseModel
from pydantic import Field
from pydantic import conint
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from voteit.components.utils import get_meeting_component_adapters
from voteit.core.role import Role
from voteit.core.validators import root_validate_roles_and_model
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.speaker.registries import list_method

_DIALECT_ROLE_COMPAT = {
    "participant": str(ROLE_PARTICIPANT),
    "moderator": str(ROLE_MODERATOR),
    "discusser": str(ROLE_DISCUSSER),
    "proposer": str(ROLE_PROPOSER),
    "potential_voter": str(ROLE_POTENTIAL_VOTER),
}


def _role_compat(v: str | Role) -> str:
    if isinstance(v, Role):
        return str(v)
    elif isinstance(v, str) and v in _DIALECT_ROLE_COMPAT:
        return _DIALECT_ROLE_COMPAT[v]
    return v


class GroupRoleSchema(BaseModel):
    title: constr(max_length=100)
    role_id: constr(max_length=100, to_lower=True)
    roles: list[str] = ()

    @validator("roles", pre=True, each_item=True)
    def role_compat(cls, v: str | Role):
        return _role_compat(v)

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


class SpeakerListSystemSchema(BaseModel):
    """
    >>> _ = SpeakerListSystemSchema(method_name='simple')
    >>> _ = SpeakerListSystemSchema(method_name='404')
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple',  safe_positions=1)
    >>> _ = SpeakerListSystemSchema(method_name='simple',  safe_positions=5)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple', meeting_roles_to_speaker=[ROLE_DISCUSSER])
    >>> SpeakerListSystemSchema(method_name='simple', meeting_roles_to_speaker=['404'])
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple', settings=None)
    >>> _ = SpeakerListSystemSchema(method_name='simple', settings={'hello': 1})
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='priority', settings={'max_times': 1})
    >>> _ = SpeakerListSystemSchema(method_name='priority', settings={})
    >>> _ = SpeakerListSystemSchema(method_name='priority', settings=None)
    """

    method_name: str
    settings: dict | None = None
    safe_positions: conint(ge=1, le=3) | None = None
    show_time: bool = False  # Will be removed?
    meeting_roles_to_speaker: list[str] = []

    @validator("method_name")
    def validate_method_name(cls, v: str):
        if v not in list_method:
            raise ValueError(f"{v} is not a valid speaker list method.")
        return v

    @validator("meeting_roles_to_speaker", pre=True, each_item=True)
    def transform_role(cls, v):
        if isinstance(v, Role):
            return str(v)
        return v

    @validator("meeting_roles_to_speaker", each_item=True)
    def validate_roles(cls, v: str):
        if v not in MeetingRoles.valid_roles.values():
            raise ValueError(f"{v} is not a valid meeting role.")
        return v

    @validator("settings")
    def check_settings(cls, v: dict | None, values: dict):
        method = list_method[values["method_name"]]
        if method.settings_schema:
            if v is None:
                v = {}
            method.settings_schema(**v)
        else:
            if v:
                raise ValueError(f"{method.name} has no settings")
        return v


class RoomSchema(BaseModel):
    title: constr(strip_whitespace=True, max_length=100) = ""
    open: bool = False
    send_sls: bool = False
    send_proposals: bool = False
    show_time: bool = False
    sls: SpeakerListSystemSchema | None = None


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
    rooms: list[RoomSchema] = []

    @validator("block_roles")
    def validate_roles(cls, v):
        if v:
            root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v

    @validator("block_roles", pre=True, each_item=True)
    def role_compat(cls, v: str | Role):
        return _role_compat(v)
