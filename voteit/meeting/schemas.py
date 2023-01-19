from pydantic import BaseModel
from pydantic import conlist
from pydantic import constr
from pydantic import validator

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
    title: constr(max_length=100)
    groupid: constr(max_length=100, to_lower=True)


class DialectSchema(BaseModel):
    """
    Settings for a meeting dialect
    
    >>> data={'title': 'Test', 'name': 'test',\
        'roles': [{'title': 'Supervisor', 'role_id': 'supervisor', 'roles': ['discusser', 'proposer']}],\
        'groups': [{'title': 'Board', 'groupid': 'board'}], 'er_policy_name': 'auto_before_poll',\
        'group_votes_active': True, 'group_roles_active': True}
    >>> DialectSchema(**data)
    DialectSchema(requires=(), title='Test', description='', name='test', roles=[GroupRoleSchema(title='Supervisor', \
    role_id='supervisor', roles=['discusser', 'proposer'], can_propose_as=False, can_discuss_as=False)],\
    groups=[GroupSchema(title='Board', groupid='board')], er_policy_name='auto_before_poll', \
    group_votes_active=True, group_roles_active=True, proposal_id_policy_name=None, installable=True)
    >>> data['roles'] = [{'title': 'Bad', 'roles': ['boho']}]
    >>> DialectSchema(**data)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    requires: list[str] = ()
    title: str
    description: str = ""
    name: str
    roles: conlist(GroupRoleSchema, unique_items=True) = []
    groups: conlist(GroupSchema, unique_items=True) = []
    er_policy_name: str | None = None
    group_votes_active: bool | None = None
    group_roles_active: bool | None = None
    proposal_id_policy_name: str | None = None
    # restricts: list[str] = ()  FIXME: We should have a system for restrictions
    installable: bool = True  # Deprecated or a base template? Set this to false
