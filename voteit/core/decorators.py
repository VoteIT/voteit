from __future__ import annotations

from typing import Optional
from typing import TYPE_CHECKING

from django.apps import apps
from django.db.transaction import get_connection
from django.db.transaction import on_commit

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


def on_transaction_commit(method):
    """
    Delay execution of a function until the database has commited.

    Remember that djangos tests use atomic transactions all the time, but doctests don't.

    Pass by referrence obj
    >>> state = {'done': False}
    >>> @on_transaction_commit
    ... def do_stuff(state):
    ...     state['done'] = True
    ...

    No transaction - will exec right away
    >>> state = {'done': False}
    >>> do_stuff(state)
    >>> state['done']
    True

    Make sure the function runs after an atomic block.
    >>> from django.db.transaction import atomic
    >>> inner_done=False
    >>> state['done'] = False
    >>> with atomic():
    ...     do_stuff(state)
    ...     inner_done=state['done']
    >>> state['done']
    True
    >>> inner_done
    False

    Exceptions should still be raised
    >>> @on_transaction_commit
    ... def loud_bang():
    ...     raise ValueError(':(')
    >>> with atomic():
    ...     loud_bang()
    Traceback (most recent call last):
    ...
    ValueError: ...
    """

    def _inner(*args, **kwargs):
        on_commit(lambda: method(*args, **kwargs))

    return _inner
