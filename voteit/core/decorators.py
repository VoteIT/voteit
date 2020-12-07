from __future__ import annotations
from typing import Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from voteit.core.role import Role
    from voteit.core.predicate import Predicate


def predicate(*args, role: Optional[Role] = None, **kwargs) -> Predicate:
    """ Decorate predicates with this instead of using rules.predicate

        The method will also add the function to the predicates-registry and wrap
        it in the Predicate class with extended functionality.

        Has the same options as rules.predicate, but accepts role as kw too.

    """
    from voteit.core.registries import predicates

    return predicates(*args, role=role, **kwargs)
