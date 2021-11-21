from __future__ import annotations

from typing import Optional
from typing import TYPE_CHECKING

from django.apps import apps
from django.db.transaction import get_connection

if TYPE_CHECKING:
    from voteit.core.role import Role
    from voteit.core.predicate import Predicate


def predicate(*args, role: Optional[Role] = None, **kwargs) -> Predicate:
    """Decorate predicates with this instead of using rules.predicate

    The method will also add the function to the predicates-registry and wrap
    it in the Predicate class with extended functionality.

    Has the same options as rules.predicate, but accepts role as kw too.

    """
    from voteit.core.registries import predicates

    return predicates(*args, role=role, **kwargs)


def receiver_all_subclasses(signal, sender=None, **kwargs):
    """
    Similar to djangos receiver decorator, but fetches models that subclassed sender
    """
    assert isinstance(sender, type), "This decorator requires sender to be specified"
    if not isinstance(signal, (list, tuple)):
        signal = (signal,)

    def _decorator(func):
        for model in apps.get_models():
            if issubclass(model, sender):
                for s in signal:
                    s.connect(func, sender=model, **kwargs)

        return func

    return _decorator


def ensure_atomic(method):
    """
    Decorator to ensure that something is within an atomic transaction.

    Remember that djangos tests use atomic transactions all the time, but doctests don't.

    >>> @ensure_atomic
    ... def hello():
    ...     pass
    ...

    >>> failed = False
    >>> try:
    ...     hello()
    ... except RuntimeError:
    ...     failed = True
    >>> failed
    True

    >>> from django.db.transaction import atomic
    >>> with atomic():
    ...     hello()
    ...
    """

    def _inner(*args, **kwargs):
        connection = get_connection()
        if not connection.in_atomic_block:
            raise RuntimeError("Must be run while atomic is enabled")
        return method(*args, **kwargs)

    return _inner
