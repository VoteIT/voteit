from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.core.schemas import PredicateOutput
from voteit.core.schemas import RoleOutput

if TYPE_CHECKING:
    from voteit.core.predicate import Predicate


class Role(str):
    """
    Create a role instance with a name. The name is used like an ID within a voteit.core.models.Roles object.
    Role inherits from str so it serializes as JSON, compares equal to plain strings, and hashes the same way.

    >>> GAMER = Role("gamer", title="Gamerz")
    >>> GAMER
    Gamerz (gamer)

    And with translation strings
    >>> from django.utils.translation import gettext_lazy
    >>> out = Role('hello', title=gettext_lazy('World')).output()
    >>> isinstance(out.title, str)
    True

    >>> GAMER = Role("gamer", title="Gamerz")
    >>> GAMER
    Gamerz (gamer)

    To use a role in a specific context, it needs to have a Model that inherits from Roles and registers an assigned field
    >>> from voteit.core.models import Roles
    >>> from voteit.core.fields import RolesField

    >>> class MyContext(Roles):
    ...     valid_roles = {GAMER: GAMER}
    ...     user = None  # Normally ForeignKey
    ...     context = None
    ...     assigned = RolesField(role_choices=valid_roles.values())

    The roles-aware class needs to register usable roles
    >>> GAMER.name in MyContext.valid_roles
    True

    Roles can have relations to other roles, causing them to be required.
    The need to be for the same context
    >>> COMPUTER_OWNER = Role("comp_owner")
    >>> GAMER.add_requirement(COMPUTER_OWNER)
    >>> GAMER.require_names
    {'comp_owner'}

    And they can produce output with pydantic:
    >>> COMPUTER_OWNER.output().dict()
    {'name': 'comp_owner', 'title': 'Comp_Owner', 'description': '',
    'require_names': [], 'predicate_info': None}

    String equality and hashing work against plain strings:
    >>> r = Role('hi')
    >>> r in {r}
    True
    >>> 'hi' == r
    True
    >>> 'hi' in {r}
    True
    >>> r in {'hi'}
    True
    """

    predicate: Predicate | None = None
    title: str
    description: str = ""
    requires: set[Role]

    def __new__(cls, name, predicate=None, title=None, description=""):
        return super().__new__(cls, name)

    def __init__(
        self,
        name,
        predicate: Predicate | None = None,
        title: str | None = None,
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

    def output(self) -> RoleOutput:
        return RoleOutput.model_validate(self)

    def __repr__(self):
        return f"{self.title} ({self.name})"

    @property
    def predicate_info(self) -> PredicateOutput | None:
        if self.predicate is not None:
            return self.predicate.output()  # Patched in registry
        return None

    def add_requirement(self, role: Role):
        assert isinstance(role, Role), "Must be a Role instance"
        self.requires.add(role)

    @property
    def require_names(self) -> set[str]:
        return {x.name for x in self.requires}
