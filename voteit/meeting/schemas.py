from pydantic import field_validator, Field, StringConstraints, BaseModel
from pydantic import model_validator

from voteit.components.utils import get_meeting_component_adapters
from voteit.core.role import Role
from voteit.core.validators import ensure_unique
from voteit.core.validators import root_validate_roles_and_model
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.speaker.registries import list_method
from typing import List
from typing_extensions import Annotated

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
    title: Annotated[str, StringConstraints(max_length=100)]
    role_id: Annotated[str, StringConstraints(max_length=100, to_lower=True)]
    roles: list[str] = ()

    @field_validator("roles", mode="before")
    @classmethod
    def role_compat(cls, v):
        if isinstance(v, (list, tuple)):
            return [_role_compat(item) for item in v]
        return v

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v):
        root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v


class GroupSchema(BaseModel):
    title: Annotated[str, StringConstraints(max_length=100)] | None = None
    groupid: Annotated[
        str, StringConstraints(max_length=100, to_lower=True, strip_whitespace=True)
    ]


class ComponentSettings(BaseModel):
    """
    >>> ComponentSettings(name='404')
    Traceback (most recent call last):
    ...
    pydantic.ValidationError: 1 validation error for ComponentSettings
    >>> from voteit.components.app.components.proposal_print import ProposalPrint
    >>> ComponentSettings(name=ProposalPrint.name)
    ComponentSettings(name='proposal_print', settings=None)
    >>> from voteit.components.app.components.message import FlashMessage
    >>> ComponentSettings(name=FlashMessage.name, settings={'msg': 'Hello'})
    ComponentSettings(name='flash_message', settings={'msg': 'Hello'})
    >>> ComponentSettings(name=FlashMessage.name)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError: 1 validation error for ComponentSettings
    >>> ComponentSettings(name=FlashMessage.name, settings={'just': 'wrong'})
    Traceback (most recent call last):
    ...
    pydantic.ValidationError: 1 validation error for ComponentSettings
    """

    name: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True)]
    settings: dict | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str):
        if v not in get_meeting_component_adapters():
            raise ValueError(f"{v} is not a meeting component name")
        return v

    # Cross-field, and the v1 form had always=True so it must still run when
    # settings is left at its default -- which a v2 field validator would not.
    @model_validator(mode="after")
    def validate_settings(self):
        try:
            adapter = get_meeting_component_adapters()[self.name]
        except KeyError:
            return self  # Will be caught by the name validator
        if adapter.schema is not None:
            if not isinstance(self.settings, dict):
                raise ValueError("missing or isn't a dict")
            adapter.schema(**self.settings)
        return self


class SpeakerListSystemSchema(BaseModel):
    """
    >>> _ = SpeakerListSystemSchema(method_name='simple')
    >>> _ = SpeakerListSystemSchema(method_name='404')
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple',  safe_positions=1)
    >>> _ = SpeakerListSystemSchema(method_name='simple',  safe_positions=5)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple', meeting_roles_to_speaker=[ROLE_DISCUSSER])
    >>> SpeakerListSystemSchema(method_name='simple', meeting_roles_to_speaker=['404'])
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='simple', settings=None)
    >>> _ = SpeakerListSystemSchema(method_name='simple', settings={'hello': 1})
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> _ = SpeakerListSystemSchema(method_name='priority', settings={'max_times': 1})
    >>> _ = SpeakerListSystemSchema(method_name='priority', settings={})
    >>> _ = SpeakerListSystemSchema(method_name='priority', settings=None)
    """

    method_name: str
    settings: dict | None = None
    safe_positions: Annotated[int, Field(ge=1, le=3)] | None = None
    show_time: bool = False  # Will be removed?
    meeting_roles_to_speaker: list[str] = []

    @field_validator("method_name")
    @classmethod
    def validate_method_name(cls, v: str):
        if v not in list_method:
            raise ValueError(f"{v} is not a valid speaker list method.")
        return v

    @field_validator("meeting_roles_to_speaker", mode="before")
    @classmethod
    def transform_role(cls, v):
        if isinstance(v, (list, tuple)):
            return [str(item) if isinstance(item, Role) else item for item in v]
        return v

    @field_validator("meeting_roles_to_speaker")
    @classmethod
    def validate_roles(cls, v: list[str]):
        for item in v:
            if item not in MeetingRoles.valid_roles.values():
                raise ValueError(f"{item} is not a valid meeting role.")
        return v

    # Cross-field. No always=True on the v1 form, so it only ran when settings
    # was actually supplied; model_fields_set preserves that.
    @model_validator(mode="after")
    def check_settings(self):
        if "settings" not in self.model_fields_set:
            return self
        method = list_method[self.method_name]
        if method.settings_schema:
            if self.settings is None:
                self.settings = {}
            method.settings_schema(**self.settings)
        elif self.settings:
            raise ValueError(f"{method.name} has no settings")
        return self


class RoomSchema(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
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
    pydantic.ValidationError:
    >>> _ = DialectSchema(block_roles=[], **data)
    >>> DialectSchema(block_roles=['jeff'], **data)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:
    """

    title: str
    description: str = ""
    name: str
    roles: Annotated[List[GroupRoleSchema], Field()] = []
    groups: Annotated[List[GroupSchema], Field()] = []
    er_policy_name: str | None = None
    group_votes_active: bool | None = None
    group_roles_active: bool | None = None
    groups_can_delegate: bool = (
        False  # Can groups delegate their vote to another group?
    )
    proposal_id_policy_name: str | None = None
    installable: bool = True  # Offer as selection for all organisations?
    requires: Annotated[
        List[Annotated[str, StringConstraints(to_lower=True, strip_whitespace=True)]],
        Field(),
    ] = []
    view_components: dict[str, str] = {}
    configure_components: list[ComponentSettings] = []
    block_components: Annotated[
        List[Annotated[str, StringConstraints(to_lower=True, strip_whitespace=True)]],
        Field(),
    ] = []
    block_roles: Annotated[
        List[Annotated[str, StringConstraints(to_lower=True, strip_whitespace=True)]],
        Field(),
    ] = []
    run_scripts: Annotated[
        List[Annotated[str, StringConstraints(strip_whitespace=True)]], Field()
    ] = []
    rooms: list[RoomSchema] = []

    @field_validator(
        "roles", "groups", "requires", "block_components", "block_roles", "run_scripts"
    )
    @classmethod
    def validate_unique(cls, v):
        return ensure_unique(v)

    @field_validator("block_roles")
    @classmethod
    def validate_roles(cls, v):
        if v:
            root_validate_roles_and_model(cls, {"model": "meeting", "roles": v})
        return v

    @field_validator("block_roles", mode="before")
    @classmethod
    def role_compat(cls, v):
        if isinstance(v, (list, tuple)):
            return [_role_compat(item) for item in v]
        return v
