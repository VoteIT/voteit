from __future__ import annotations

from typing import Type, Set, TYPE_CHECKING, Optional

from voteit.core.schemas import RoleOutput, PredicateOutput

if TYPE_CHECKING:
    from voteit.core.models import Roles
    from voteit.core.predicate import Predicate


class Role:
    """
    Create a role instance with a name. The name is used like an ID within a voteit.core.models.Roles object.
    >>> GAMER = Role("gamer", title="Gamerz")
    >>> GAMER
    gamer

    To use a role in a specific context, it needs to have a Model that inherits from Roles
    >>> from voteit.core.models import Roles

    >>> class MyContext(Roles):
    ...     user = None  # Normally ForeignKey
    ...     context = None

    The roles-aware class needs to register usable roles
    >>> MyContext.add_valid(GAMER)
    >>> GAMER in MyContext.valid_roles
    True

    They can only be added once and to one context
    >>> MyContext.add_valid(GAMER)
    Traceback (most recent call last):
    ...
    AssertionError: Role already assigned as valid choice on another Roles model

    Roles can have relations to other roles, causing them to be required.
    The need to be for the same context
    >>> COMPUTER_OWNER = Role("comp_owner")
    >>> MyContext.add_valid(COMPUTER_OWNER)
    >>> GAMER.add_requirement(COMPUTER_OWNER)
    >>> GAMER.require_names
    {'comp_owner'}

    And they can produce output with pydantic:
    >>> COMPUTER_OWNER.output().dict()
    {'name': 'comp_owner', 'title': 'Comp_Owner', 'description': '',
    'require_names': [], 'roles_cls_name': 'voteit.core.role.MyContext', 'predicate_info': None}
    """
    name: str
    predicate: Optional[Predicate] = None
    title: str
    description: str = ""
    roles_cls: Type[Roles]
    requires: Set[Role]

    def __init__(
        self,
        name,
        predicate: Optional[Predicate] = None,
        title: Optional[str] = None,
        description: str = "",
    ):
        self.name = name
        if predicate:
            self.predicate = predicate
        if title is None:
            title = name.title()
        self.title = title
        if description:
            self.description = description
        self.requires = set()
        self.roles_cls = None  # Will be set when this is attached to a Roles class

    def output(self) -> RoleOutput:
        return RoleOutput.from_orm(self)

    def __str__(self):
        return self.name

    __repr__ = __str__

    @property
    def predicate_info(self) -> Optional[PredicateOutput]:
        if self.predicate is not None:
            return self.predicate.output()  # Patched in registry
        return None

    def add_requirement(self, role: Role):
        assert isinstance(role, Role), "Must be a Role instance"
        assert (
            self.roles_cls is not None
        ), "Assign this role to a Roles context first, for instance MeetingRoles"
        assert isinstance(role, Role)
        assert (
            role.roles_cls == self.roles_cls
        ), "Requirements context (roles_cls) doesn't match"
        self.requires.add(role)

    @property
    def require_names(self) -> Set[str]:
        return set([x.name for x in self.requires])

    @property
    def roles_cls_name(self) -> Optional[str]:
        return f"{self.roles_cls.__module__}.{self.roles_cls.__name__}"

    def __eq__(self, other):
        if isinstance(other, Role):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        return False

    def __hash__(self):
        return hash(self.name)
