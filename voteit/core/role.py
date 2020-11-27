from __future__ import annotations
from typing import Type, Set, TYPE_CHECKING, List

from pydantic import Field, BaseModel

if TYPE_CHECKING:
    from voteit.core.models import Roles


class Role:
    name: str
    title: str
    description: str
    requires: Set[Role]
    roles_cls: Type[Roles] = Field

    def __init__(self, name, title=None, description=""):
        self.name = name
        if title is None:
            title = name.title()
        self.title = title
        self.description = description
        self.requires = set()
        self.roles_cls = None  # Will be set when this is attached to a Roles class

    def add_requirement(self, role: Role):
        assert (
            self.roles_cls is not None
        ), "Assign this role to a Roles context first, for instance MeetingRoles"
        assert isinstance(role, Role)
        assert (
            role.roles_cls == self.roles_cls
        ), "Requirements context (roles_cls) doesn't match"
        self.requires.add(role)

    def __repr__(self):
        return self.name

    def as_output(self):
        return RoleOutput(
            name=self.name,
            title=self.title,
            description=self.description,
            requires=[x.name for x in self.requires]
        )


class RoleOutput(BaseModel):
    name: str
    title: str
    description: str
    requires: List[str]
